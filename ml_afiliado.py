#!/usr/bin/env python3
"""
Gerador de posts para afiliados do Mercado Livre.

Cole o seu link de afiliado (ex: https://meli.la/xxxx) e o script:
  1. segue o redirecionamento até a página do produto
  2. extrai nome, preço anterior, preço novo e imagem
  3. gera um texto chamativo pronto para postar
  4. baixa a imagem e copia o texto para a área de transferência

Instalação:
    pip install requests beautifulsoup4 pyperclip

Uso:
    python ml_afiliado.py                      # modo interativo (cola vários links)
    python ml_afiliado.py "https://meli.la/xxxx"
    python ml_afiliado.py "https://meli.la/xxxx" --modelo 2
"""

import argparse
import json
import os
import random
import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    import pyperclip
except ImportError:  # copiar para a área de transferência é opcional
    pyperclip = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PASTA_IMAGENS = "imagens"


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def brl(valor):
    """1234.5 -> 'R$ 1.234,50'"""
    if valor is None:
        return ""
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def parse_preco(texto):
    """Converte '1.299,90' / '1299.90' / '1.299' em float."""
    if texto is None:
        return None
    t = str(texto).strip()
    t = re.sub(r"[^\d.,]", "", t)
    if not t:
        return None
    if "," in t:  # formato brasileiro
        t = t.replace(".", "").replace(",", ".")
    else:
        # só ponto: se houver 3 dígitos após o último ponto é milhar (1.299)
        partes = t.split(".")
        if len(partes) > 1 and len(partes[-1]) == 3:
            t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def preco_de_elemento(el):
    """Lê fração + centavos de um bloco andes-money-amount."""
    if el is None:
        return None
    fr = el.select_one(".andes-money-amount__fraction")
    if not fr:
        return None
    inteiro = re.sub(r"\D", "", fr.get_text())
    if not inteiro:
        return None
    cents = el.select_one(".andes-money-amount__cents")
    centavos = re.sub(r"\D", "", cents.get_text()) if cents else "00"
    return float(f"{inteiro}.{centavos.ljust(2, '0')[:2]}")


# ----------------------------------------------------------------------------
# Extração
# ----------------------------------------------------------------------------
def baixar_pagina(url):
    sessao = requests.Session()
    sessao.headers.update(HEADERS)
    resp = sessao.get(url, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    return resp.url, resp.text


def achar_produto_jsonld(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            dados = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        itens = dados if isinstance(dados, list) else [dados]
        for item in itens:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
            if isinstance(item, dict) and "@graph" in item:
                for g in item["@graph"]:
                    if isinstance(g, dict) and g.get("@type") == "Product":
                        return g
    return None


def extrair_dados(html, url_final):
    soup = BeautifulSoup(html, "html.parser")
    nome = imagem = None
    preco_novo = preco_antigo = None

    # 1) JSON-LD (mais confiável)
    produto = achar_produto_jsonld(soup)
    if produto:
        nome = produto.get("name")
        img = produto.get("image")
        imagem = img[0] if isinstance(img, list) and img else img
        ofertas = produto.get("offers")
        if isinstance(ofertas, list) and ofertas:
            ofertas = ofertas[0]
        if isinstance(ofertas, dict):
            preco_novo = parse_preco(ofertas.get("price"))

    # 2) Metatags como reserva
    if not nome:
        og = soup.find("meta", property="og:title")
        nome = og["content"] if og and og.get("content") else (
            soup.title.get_text(strip=True) if soup.title else None
        )
    if not imagem:
        og = soup.find("meta", property="og:image")
        imagem = og["content"] if og and og.get("content") else None

    # 3) Preço anterior (riscado) e preço atual pelo HTML
    antigo_el = soup.select_one(".andes-money-amount--previous")
    preco_antigo = preco_de_elemento(antigo_el)

    if preco_novo is None:
        for el in soup.select(".andes-money-amount"):
            if "andes-money-amount--previous" in (el.get("class") or []):
                continue
            if el.find_parent(class_=re.compile("previous")):
                continue
            p = preco_de_elemento(el)
            if p:
                preco_novo = p
                break

    if preco_antigo and preco_novo and preco_antigo <= preco_novo:
        preco_antigo = None  # não há desconto real

    # Parcelamento (opcional, enfeita o texto)
    parcelas = None
    el_parc = soup.select_one(".ui-pdp-price__second-line__label, .ui-pdp-price__subtitles")
    if el_parc:
        parcelas = re.sub(r"\s+", " ", el_parc.get_text(" ", strip=True))

    return {
        "nome": (nome or "").strip(),
        "preco_novo": preco_novo,
        "preco_antigo": preco_antigo,
        "imagem": imagem,
        "parcelas": parcelas,
        "url": url_final,
    }


# ----------------------------------------------------------------------------
# Texto de divulgação
# ----------------------------------------------------------------------------
def encurtar_nome(nome, limite=90):
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome if len(nome) <= limite else nome[: limite - 1].rstrip() + "…"


def gerar_texto(d, link_afiliado, modelo=None):
    nome = encurtar_nome(d["nome"])
    novo, antigo = d["preco_novo"], d["preco_antigo"]
    desconto = None
    economia = None
    if novo and antigo:
        desconto = round((1 - novo / antigo) * 100)
        economia = antigo - novo

    linha_preco = ""
    if antigo and novo:
        linha_preco = f"❌ De: ~{brl(antigo)}~\n✅ Por: *{brl(novo)}*"
    elif novo:
        linha_preco = f"💰 Por apenas: *{brl(novo)}*"

    linha_desc = f"🔥 {desconto}% OFF" if desconto and desconto > 0 else ""
    linha_eco = f"💸 Economize {brl(economia)}" if economia else ""
    linha_parc = f"💳 {d['parcelas']}" if d.get("parcelas") else ""

    SEP = "\n"  # separador de parágrafo (vira uma linha em branco)

    def montar(*blocos):
        # descarta linhas opcionais vazias, mantém os separadores (SEP)
        texto = "\n".join(b for b in blocos if b)
        return re.sub(r"\n{3,}", "\n\n", texto).strip() + "\n"

    modelos = [
        # 1 — urgência
        montar(
            "🚨 ACHADINHO IMPERDÍVEL! 🚨" if not desconto else f"🚨 {desconto}% DE DESCONTO! CORRE! 🚨",
            SEP,
            f"🛒 {nome}",
            SEP,
            linha_preco,
            linha_eco,
            linha_parc,
            SEP,
            "⏰ Promoção por tempo limitado, o estoque pode acabar!",
            f"👉 Compre aqui: {link_afiliado}",
        ),
        # 2 — oferta relâmpago
        montar(
            "⚡ OFERTA RELÂMPAGO ⚡",
            SEP,
            f"{nome}",
            SEP,
            linha_desc,
            linha_preco,
            linha_parc,
            SEP,
            "Quem viu primeiro leva mais barato 😉",
            f"🔗 {link_afiliado}",
        ),
        # 3 — curiosidade / prova social
        montar(
            "😱 Olha esse preço!!",
            SEP,
            f"{nome}",
            SEP,
            linha_preco,
            linha_desc,
            linha_eco,
            SEP,
            "Já garantiu o seu? Esse tipo de oferta some rápido 🏃‍♂️💨",
            f"🛍️ Link: {link_afiliado}",
        ),
        # 4 — direto e limpo
        montar(
            f"✨ {nome}",
            SEP,
            linha_preco,
            linha_desc,
            linha_parc,
            SEP,
            f"Aproveite 👉 {link_afiliado}",
        ),
    ]

    if modelo and 1 <= modelo <= len(modelos):
        texto = modelos[modelo - 1]
    else:
        texto = random.choice(modelos)

    texto = re.sub(r"\n{3,}", "\n\n", texto)
    texto += "\n_Preço e disponibilidade podem mudar a qualquer momento._"
    return texto


# ----------------------------------------------------------------------------
# Imagem
# ----------------------------------------------------------------------------
def baixar_imagem(url_imagem, nome_produto):
    if not url_imagem:
        return None
    os.makedirs(PASTA_IMAGENS, exist_ok=True)
    ext = os.path.splitext(urlparse(url_imagem).path)[1] or ".jpg"
    base = re.sub(r"[^a-zA-Z0-9]+", "_", nome_produto)[:40].strip("_") or "produto"
    caminho = os.path.join(PASTA_IMAGENS, base + ext)
    try:
        r = requests.get(url_imagem, headers=HEADERS, timeout=20)
        r.raise_for_status()
        with open(caminho, "wb") as f:
            f.write(r.content)
        return caminho
    except requests.RequestException as e:
        print(f"⚠️  Não consegui baixar a imagem: {e}")
        return None


# ----------------------------------------------------------------------------
# Fluxo principal
# ----------------------------------------------------------------------------
def processar(link, modelo=None):
    link = link.strip()
    if not link.startswith("http"):
        print("⚠️  Cole um link completo começando com http(s)://")
        return

    print("🔎 Buscando informações do produto...")
    try:
        url_final, html = baixar_pagina(link)
    except requests.RequestException as e:
        print(f"❌ Erro ao abrir o link: {e}")
        return

    dados = extrair_dados(html, url_final)

    if not dados["nome"] or not dados["preco_novo"]:
        print("⚠️  Não consegui ler tudo automaticamente (o site pode ter bloqueado ou")
        print("    o link de afiliado abre uma página de vitrine em vez do produto).")
        print("    Dica: abra o link no navegador, copie o endereço da página do produto")
        print("    e cole aqui no lugar.")
        print(f"    Lido até agora: {dados}")
        return

    texto = gerar_texto(dados, link, modelo)
    caminho_img = baixar_imagem(dados["imagem"], dados["nome"])

    print("\n" + "=" * 60)
    print(f"Produto:        {dados['nome']}")
    print(f"Preço anterior: {brl(dados['preco_antigo']) or '— (sem desconto detectado)'}")
    print(f"Preço novo:     {brl(dados['preco_novo'])}")
    print(f"Imagem:         {caminho_img or dados['imagem'] or '—'}")
    print("=" * 60)
    print("\n📋 TEXTO PRONTO PARA POSTAR:\n")
    print(texto)

    if pyperclip:
        try:
            pyperclip.copy(texto)
            print("✅ Texto copiado para a área de transferência!")
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Gerador de posts de afiliado Mercado Livre")
    ap.add_argument("link", nargs="?", help="seu link de afiliado")
    ap.add_argument("--modelo", type=int, help="modelo de texto (1 a 4); padrão: aleatório")
    args = ap.parse_args()

    if args.link:
        processar(args.link, args.modelo)
        return

    print("Cole seu link de afiliado (ou digite 'sair'):")
    while True:
        try:
            link = input("\n🔗 Link: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if link.lower() in ("sair", "exit", "q"):
            break
        if link:
            processar(link, args.modelo)


if __name__ == "__main__":
    sys.exit(main())
