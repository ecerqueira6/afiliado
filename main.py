"""
Afiliado ML - app Android (Kivy) que reaproveita a lógica do ml_afiliado.py
"""
import re
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import ml_afiliado as ml

Window.softinput_mode = "below_target"


def extrair_url(texto):
    """Pega o primeiro http(s)://... de qualquer texto colado."""
    m = re.search(r"https?://\S+", texto or "")
    return m.group(0).rstrip(").,;") if m else ""


def compartilhar_android(texto):
    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        String = autoclass("java.lang.String")
        intent = Intent()
        intent.setAction(Intent.ACTION_SEND)
        intent.putExtra(Intent.EXTRA_TEXT, String(texto))
        intent.setType("text/plain")
        chooser = Intent.createChooser(intent, String("Compartilhar oferta"))
        PythonActivity.mActivity.startActivity(chooser)
        return True
    except Exception:
        return False


def botao(texto, cor=(0.1, 0.5, 0.9, 1)):
    return Button(
        text=texto,
        size_hint_y=None,
        height="48dp",
        background_normal="",
        background_color=cor,
        color=(1, 1, 1, 1),
        bold=True,
    )


class AfiliadoApp(App):
    title = "Afiliado ML"

    def build(self):
        self.dados = None
        self.link = ""
        self.modelo = 0  # 0 = aleatório

        raiz = BoxLayout(orientation="vertical", padding="12dp", spacing="8dp")

        self.entrada = TextInput(
            hint_text="Cole aqui seu link de afiliado",
            multiline=False,
            size_hint_y=None,
            height="46dp",
        )
        raiz.add_widget(self.entrada)

        linha = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        b_colar = botao("Colar", (0.35, 0.35, 0.4, 1))
        b_colar.bind(on_release=self.colar)
        b_gerar = botao("Gerar texto", (0.1, 0.65, 0.3, 1))
        b_gerar.bind(on_release=self.gerar)
        linha.add_widget(b_colar)
        linha.add_widget(b_gerar)
        raiz.add_widget(linha)

        self.status = Label(
            text="", size_hint_y=None, height="24dp", color=(1, 0.85, 0.3, 1)
        )
        raiz.add_widget(self.status)

        rolagem = ScrollView()
        corpo = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing="8dp", padding="2dp"
        )
        corpo.bind(minimum_height=corpo.setter("height"))

        self.imagem = AsyncImage(size_hint_y=None, height="220dp", allow_stretch=True)
        corpo.add_widget(self.imagem)

        self.resumo = Label(
            text="", size_hint_y=None, halign="left", valign="top", markup=True
        )
        self.resumo.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None)),
            texture_size=lambda w, v: setattr(w, "height", v[1] + 8),
        )
        corpo.add_widget(self.resumo)

        self.texto = TextInput(
            hint_text="O texto da oferta aparece aqui (você pode editar)",
            size_hint_y=None,
            height="320dp",
        )
        corpo.add_widget(self.texto)

        linha2 = BoxLayout(size_hint_y=None, height="48dp", spacing="8dp")
        b_outro = botao("Outro estilo", (0.55, 0.3, 0.75, 1))
        b_outro.bind(on_release=self.outro_estilo)
        b_copiar = botao("Copiar")
        b_copiar.bind(on_release=self.copiar)
        b_comp = botao("Compartilhar", (0.1, 0.65, 0.3, 1))
        b_comp.bind(on_release=self.compartilhar)
        linha2.add_widget(b_outro)
        linha2.add_widget(b_copiar)
        linha2.add_widget(b_comp)
        corpo.add_widget(linha2)

        b_img = botao("Abrir imagem (segure para salvar)", (0.35, 0.35, 0.4, 1))
        b_img.bind(on_release=self.abrir_imagem)
        corpo.add_widget(b_img)

        rolagem.add_widget(corpo)
        raiz.add_widget(rolagem)
        return raiz

    # ---- ações -----------------------------------------------------------
    def msg(self, texto):
        self.status.text = texto

    def colar(self, *_):
        try:
            self.entrada.text = extrair_url(Clipboard.paste()) or (Clipboard.paste() or "")
        except Exception:
            self.msg("Não consegui ler a área de transferência")

    def gerar(self, *_):
        link = extrair_url(self.entrada.text)
        if not link:
            self.msg("Cole um link começando com http(s)://")
            return
        self.link = link
        self.msg("Buscando informações do produto...")
        threading.Thread(target=self._buscar, args=(link,), daemon=True).start()

    def _buscar(self, link):
        try:
            url_final, html = ml.baixar_pagina(link)
            dados = ml.extrair_dados(html, url_final)
        except Exception as e:  # rede, bloqueio etc.
            Clock.schedule_once(lambda dt: self.msg(f"Erro ao abrir o link: {e}"))
            return
        Clock.schedule_once(lambda dt: self._mostrar(dados))

    def _mostrar(self, dados):
        if not dados["nome"] or not dados["preco_novo"]:
            self.msg("Não consegui ler o produto. Tente o link da página do produto.")
            return
        self.dados = dados
        self.msg("Pronto!")
        antigo = ml.brl(dados["preco_antigo"]) or "sem desconto detectado"
        self.resumo.text = (
            f"[b]{dados['nome']}[/b]\n"
            f"Preço anterior: {antigo}\n"
            f"Preço novo: [b]{ml.brl(dados['preco_novo'])}[/b]"
        )
        self.imagem.source = dados["imagem"] or ""
        self._gerar_texto()

    def _gerar_texto(self):
        if not self.dados:
            return
        self.texto.text = ml.gerar_texto(self.dados, self.link, self.modelo or None)

    def outro_estilo(self, *_):
        if not self.dados:
            self.msg("Gere um texto primeiro")
            return
        self.modelo = self.modelo % 4 + 1
        self._gerar_texto()
        self.msg(f"Estilo {self.modelo} de 4")

    def copiar(self, *_):
        if not self.texto.text:
            self.msg("Nada para copiar")
            return
        Clipboard.copy(self.texto.text)
        self.msg("Texto copiado!")

    def compartilhar(self, *_):
        if not self.texto.text:
            self.msg("Nada para compartilhar")
            return
        if not compartilhar_android(self.texto.text):
            Clipboard.copy(self.texto.text)
            self.msg("Compartilhar indisponível, texto copiado")

    def abrir_imagem(self, *_):
        if self.dados and self.dados.get("imagem"):
            webbrowser.open(self.dados["imagem"])
        else:
            self.msg("Sem imagem para abrir")


if __name__ == "__main__":
    AfiliadoApp().run()
