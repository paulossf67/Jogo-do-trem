"""
Template de janela principal seguindo o padrão visual do Sistema ASSIDESP:
cabeçalho azul (hora / título / busca / data), menu lateral fixo,
dashboard inicial com cards de indicadores + avisos, e rodapé de status.

Substitua os pontos marcados com "PERSONALIZE" pela lógica/dados do seu projeto.
"""
import logging
import random
import threading
import traceback
from datetime import datetime

import customtkinter as ctk

try:
    import psutil
except ImportError:
    psutil = None

from cores import Cores

# PERSONALIZE: em produção, troque para logging em arquivo (FileHandler)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Sistema de Controle")  # PERSONALIZE: nome do projeto
        self.geometry("1200x750")
        try:
            self.state("zoomed")
        except Exception:
            pass

        # Evita que exceções em callbacks (ex.: self.after de threads em background)
        # derrubem o app silenciosamente quando empacotado sem console (PyInstaller --noconsole)
        self.report_callback_exception = self._handle_callback_exception

        self.usuario_nome = "Usuário"  # PERSONALIZE: nome do usuário logado

        self._montar_cabecalho()
        self._montar_rodape()
        self._montar_layout_principal()

        self.atualizar_tempo()
        self.atualizar_status_sistema()
        self.atualizar_status_conexao()

        self.voltar_inicio()

    def _handle_callback_exception(self, exc_type, exc_value, exc_traceback):
        """PERSONALIZE: troque por logging em arquivo/e-mail conforme o projeto."""
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logging.error(f"Erro não tratado em callback da UI:\n{tb_str}")

    # ------------------------------------------------------------------ #
    # CABEÇALHO
    # ------------------------------------------------------------------ #
    def _montar_cabecalho(self):
        self.header = ctk.CTkFrame(self, corner_radius=0, height=60, fg_color=Cores.PRIMARIO)
        self.header.pack(side="top", fill="x")

        self.lbl_hora = ctk.CTkLabel(self.header, text="", font=("Arial", 16), text_color="white")
        self.lbl_hora.pack(side="left", padx=20)

        self.lbl_titulo = ctk.CTkLabel(self.header, text="SISTEMA DE CONTROLE",  # PERSONALIZE
                                        font=("Arial", 20, "bold"), text_color="white")
        self.lbl_titulo.place(relx=0.5, rely=0.5, anchor="center")

        self.lbl_data = ctk.CTkLabel(self.header, text="", font=("Arial", 16), text_color="white")
        self.lbl_data.pack(side="right", padx=20)

        self.entry_global_search = ctk.CTkEntry(self.header, placeholder_text="Busca rápida",
                                                 width=280, fg_color="white",
                                                 text_color="#333333", border_width=0)
        self.entry_global_search.pack(side="right", padx=10)
        self.entry_global_search.bind("<Return>", self._busca_global)

        btn_busca = ctk.CTkButton(self.header, text="🔍", width=40, command=self._busca_global,
                                   fg_color="#14508c", hover_color="#0d3c6b", text_color="white")
        btn_busca.pack(side="right")

    def _busca_global(self, event=None):
        termo = self.entry_global_search.get().strip()
        if not termo:
            return
        # PERSONALIZE: pesquisar o termo na sua fonte de dados e abrir o registro encontrado
        print(f"Buscar: {termo}")
        self.entry_global_search.delete(0, "end")

    # ------------------------------------------------------------------ #
    # RODAPÉ
    # ------------------------------------------------------------------ #
    def _montar_rodape(self):
        self.footer = ctk.CTkFrame(self, corner_radius=0, height=30)
        self.footer.pack(side="bottom", fill="x")

        self.lbl_status_sistema = ctk.CTkLabel(self.footer, text="CPU: - | RAM: -", font=("Arial", 12))
        self.lbl_status_sistema.pack(side="left", padx=20)

        self.lbl_status_conexao = ctk.CTkLabel(self.footer, text="Verificando...", font=("Arial", 12, "bold"))
        self.lbl_status_conexao.pack(side="left", padx=20)

        self.lbl_creditos = ctk.CTkLabel(self.footer, text="Sistema desenvolvido por Seu Nome",  # PERSONALIZE
                                          font=("Arial", 12))
        self.lbl_creditos.pack(side="right", padx=20)

    # ------------------------------------------------------------------ #
    # LAYOUT PRINCIPAL (sidebar + conteúdo)
    # ------------------------------------------------------------------ #
    def _montar_layout_principal(self):
        self.main_container = ctk.CTkFrame(self, corner_radius=0)
        self.main_container.pack(fill="both", expand=True)

        self.sidebar_frame = ctk.CTkFrame(self.main_container, width=200, corner_radius=0)
        self.sidebar_frame.pack(side="left", fill="y")

        self.content_frame = ctk.CTkFrame(self.main_container, corner_radius=0, fg_color="transparent")
        self.content_frame.pack(side="right", fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(self.sidebar_frame, text="MENU PRINCIPAL", font=("Arial", 13, "bold"),
                     text_color=Cores.PRIMARIO).pack(pady=(20, 15))

        # PERSONALIZE: troque os itens/comandos pelos módulos do seu projeto
        self.btn_inicio = ctk.CTkButton(self.sidebar_frame, text="🏠  Início", anchor="w",
                                         command=self.voltar_inicio)
        self.btn_inicio.pack(pady=(0, 10), padx=20, fill="x")

        itens_menu = [
            ("📅  Agenda", self.abrir_modulo_generico),
            ("👤  Cadastro", self.abrir_modulo_generico),
            ("💰  Financeiro", self.abrir_modulo_generico),
            ("📊  Relatórios", self.abrir_modulo_generico),
        ]
        for texto, comando in itens_menu:
            ctk.CTkButton(self.sidebar_frame, text=texto, anchor="w", command=comando) \
                .pack(pady=10, padx=20, fill="x")

        self.btn_sair = ctk.CTkButton(self.sidebar_frame, text="🚪  Sair do Sistema", anchor="w",
                                       command=self.quit, fg_color=Cores.PERIGO, hover_color="#a83232")
        self.btn_sair.pack(side="bottom", pady=20, padx=20, fill="x")

    def abrir_modulo_generico(self):
        self.limpar_conteudo()
        ctk.CTkLabel(self.content_frame, text="Módulo em construção", font=("Arial", 20, "bold")).pack(pady=40)

    def limpar_conteudo(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    # ------------------------------------------------------------------ #
    # TELA INICIAL (dashboard)
    # ------------------------------------------------------------------ #
    def voltar_inicio(self):
        self.limpar_conteudo()

        scroll_home = ctk.CTkScrollableFrame(self.content_frame, fg_color="transparent")
        scroll_home.pack(fill="both", expand=True)

        primeiro_nome = self.usuario_nome.split()[0] if self.usuario_nome.strip() else "Usuário"
        ctk.CTkLabel(scroll_home, text=f"Bem-vindo de volta, {primeiro_nome}!",
                     font=("Arial", 26, "bold")).pack(pady=(10, 20), anchor="w", padx=20)

        summary_grid = ctk.CTkFrame(scroll_home, fg_color="transparent")
        summary_grid.pack(fill="x", padx=20)
        summary_grid.grid_columnconfigure((0, 1, 2), weight=1)

        def create_stat_card(parent, row, col, title, value, color):
            card = ctk.CTkFrame(parent, fg_color=color, corner_radius=10, height=100)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            card.grid_propagate(False)
            ctk.CTkLabel(card, text=title, font=("Arial", 14), text_color="white").pack(pady=(15, 0))
            lbl_valor = ctk.CTkLabel(card, text=value, font=("Arial", 24, "bold"), text_color="white")
            lbl_valor.pack()
            return lbl_valor

        # Cards exibidos com placeholder; valores reais chegam em background
        # (evita travar a tela mais visitada do sistema com consultas síncronas)
        lbl_indicador1 = create_stat_card(summary_grid, 0, 0, "Indicador 1", "...", "#1f6aa5")
        lbl_indicador2 = create_stat_card(summary_grid, 0, 1, "Indicador 2", "...", "#2d5f56")
        lbl_indicador3 = create_stat_card(summary_grid, 0, 2, "Saldo", "...", "#28a745")

        def buscar_estatisticas_home():
            # PERSONALIZE: troque pelas consultas reais (banco de dados, API, etc.)
            return {"indicador1": 0, "indicador2": 0, "saldo": 0.0}

        def exibir_estatisticas_home(dados):
            if not scroll_home.winfo_exists():
                return
            lbl_indicador1.configure(text=str(dados["indicador1"]))
            lbl_indicador2.configure(text=str(dados["indicador2"]))
            saldo = dados["saldo"]
            lbl_indicador3.configure(text=f"R$ {saldo:,.2f}")
            lbl_indicador3.master.configure(fg_color="#28a745" if saldo >= 0 else "#d9534f")

        def worker_estatisticas_home():
            resultado = buscar_estatisticas_home()
            if self.winfo_exists():
                self.after(0, lambda: exibir_estatisticas_home(resultado))

        threading.Thread(target=worker_estatisticas_home, daemon=True).start()

        ctk.CTkLabel(scroll_home, text="Avisos Importantes", font=("Arial", 18, "bold")) \
            .pack(pady=(30, 10), anchor="w", padx=20)

        alerts_frame = ctk.CTkFrame(scroll_home, fg_color="transparent")
        alerts_frame.pack(fill="x", padx=20)

        alertas = self._buscar_alertas()  # PERSONALIZE: lista real de avisos/pendências
        if not alertas:
            ctk.CTkLabel(alerts_frame, text="Nenhum alerta crítico para hoje. Bom trabalho!",
                         font=("Arial", 14, "italic"), text_color="gray").pack(pady=10)
        else:
            for alerta in alertas:
                self._criar_card_alerta(alerts_frame, alerta)

        frases = [
            "O sucesso é a soma de pequenos esforços repetidos dia após dia.",
            "A persistência é o caminho do êxito!",
            "Sua única limitação é a sua imaginação.",
            "Grandes coisas nunca vêm de zonas de conforto.",
        ]
        ctk.CTkLabel(scroll_home, text=f'"{random.choice(frases)}"', font=("Arial", 14, "italic"),
                     text_color="gray50").pack(pady=50)

    def _buscar_alertas(self):
        # PERSONALIZE: retorne avisos reais, ex.:
        # [{"texto": "Pagamento X: 10/07/2026 (Faltam 5 dias)", "acao": self.ir_para_calendario}]
        return []

    def _criar_card_alerta(self, parent, alerta):
        card = ctk.CTkFrame(parent, fg_color=Cores.ALERTA, corner_radius=6)
        card.pack(fill="x", pady=5)
        ctk.CTkLabel(card, text=f"⚠  {alerta['texto']}", font=("Arial", 13),
                     text_color="white").pack(side="left", padx=15, pady=10)
        if alerta.get("acao"):
            ctk.CTkButton(card, text=alerta.get("botao_texto", "Ver detalhes"), fg_color="white",
                          text_color="#333333", hover_color="#dddddd",
                          command=alerta["acao"]).pack(side="right", padx=15, pady=8)

    # ------------------------------------------------------------------ #
    # RELÓGIO / STATUS (rodapé)
    # ------------------------------------------------------------------ #
    def atualizar_tempo(self):
        agora = datetime.now()
        self.lbl_hora.configure(text=agora.strftime("%H:%M:%S"))
        self.lbl_data.configure(text=agora.strftime("%d/%m/%Y"))
        self.after(1000, self.atualizar_tempo)

    def atualizar_status_sistema(self):
        if psutil:
            try:
                import os
                processo = psutil.Process(os.getpid())
                mem_mb = processo.memory_info().rss / 1024 / 1024
                cpu = processo.cpu_percent(interval=None)
                self.lbl_status_sistema.configure(text=f"CPU: {cpu:.1f}% | RAM: {mem_mb:.1f} MB")
            except Exception:
                self.lbl_status_sistema.configure(text="Erro ao ler status")
        else:
            self.lbl_status_sistema.configure(text="Instale 'psutil' para ver status")
        self.after(2000, self.atualizar_status_sistema)

    def atualizar_status_conexao(self):
        def checar():
            # PERSONALIZE: troque pela checagem real de internet/banco de dados
            net_ok, db_ok = True, True
            if self.winfo_exists():
                self.after(0, lambda: self._atualizar_status_conexao_ui(net_ok, db_ok))

        threading.Thread(target=checar, daemon=True).start()
        self.after(15000, self.atualizar_status_conexao)

    def _atualizar_status_conexao_ui(self, net_ok, db_ok):
        self.lbl_status_conexao.configure(text=f"NET: {'OK' if net_ok else 'OFF'} | DB: {'OK' if db_ok else 'OFF'}")
        if net_ok and db_ok:
            self.lbl_status_conexao.configure(text_color="#32a852")
        elif net_ok or db_ok:
            self.lbl_status_conexao.configure(text_color="#E0A800")
        else:
            self.lbl_status_conexao.configure(text_color="#d9534f")


if __name__ == "__main__":
    app = App()
    app.mainloop()
