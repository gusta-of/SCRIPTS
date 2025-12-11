import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import re

# PYTHON 3.14

def analisar_logs_com_contexto(caminho_arquivo, contexto=5):
    padrao_excecao = re.compile(r'Exception|Error|Traceback', re.IGNORECASE)
    blocos = []

    try:
        with open(caminho_arquivo, 'r', encoding='utf-8', errors='ignore') as file:
            linhas = file.readlines()
    except FileNotFoundError:
        return f"Arquivo '{caminho_arquivo}' não encontrado."

    for i, linha in enumerate(linhas):
        if padrao_excecao.search(linha):
            inicio = max(i - contexto, 0)
            fim = min(i + contexto + 1, len(linhas))
            bloco = ''.join(linhas[inicio:fim]).strip()
            blocos.append(bloco)

    if blocos:
        return '\n' + '\n'.join(['-'*50 + '\n' + bloco for bloco in blocos])
    else:
        return "Nenhuma exceção encontrada no log."

# ================= Funções da interface =================
def abrir_arquivo():
    global conteudo_completo
    caminho_arquivo = filedialog.askopenfilename(filetypes=[("Todos os arquivos", "*")])
    if caminho_arquivo:
        label_arquivo.config(text=f"Arquivo analisado: {caminho_arquivo}")
        conteudo_completo = analisar_logs_com_contexto(caminho_arquivo)
        atualizar_caixa_texto(conteudo_completo)

def atualizar_caixa_texto(texto):
    caixa_texto.config(state='normal')
    caixa_texto.delete(1.0, tk.END)
    caixa_texto.insert(tk.END, texto)
    caixa_texto.config(state='disabled')

def limpar_caixa():
    global conteudo_completo, highlights
    conteudo_completo = ""
    highlights = []
    atualizar_caixa_texto("")
    label_arquivo.config(text="Nenhum arquivo selecionado")
    entry_busca.delete(0, tk.END)

def exportar_excecoes():
    conteudo = caixa_texto.get(1.0, tk.END).strip()
    if not conteudo:
        messagebox.showwarning("Aviso", "Não há exceções para exportar!")
        return

    caminho_salvar = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Arquivos de texto", "*.txt")],
        title="Salvar exceções"
    )
    if caminho_salvar:
        try:
            with open(caminho_salvar, 'w', encoding='utf-8') as f:
                f.write(conteudo)
            messagebox.showinfo("Sucesso", f"Exceções exportadas para {caminho_salvar}")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível salvar o arquivo: {e}")

# ================= Sistema de busca com navegação =================
highlights = []
current_highlight_index = -1

def buscar_palavra_chave():
    global highlights, current_highlight_index
    palavra = entry_busca.get().strip()
    atualizar_caixa_texto(conteudo_completo)
    caixa_texto.tag_remove("destaque", "1.0", tk.END)
    highlights = []
    current_highlight_index = -1

    if not palavra:
        return

    start_pos = "1.0"
    while True:
        start_pos = caixa_texto.search(palavra, start_pos, tk.END, nocase=True)
        if not start_pos:
            break
        end_pos = f"{start_pos}+{len(palavra)}c"
        caixa_texto.tag_add("destaque", start_pos, end_pos)
        highlights.append((start_pos, end_pos))
        start_pos = end_pos

    caixa_texto.tag_config("destaque", background="yellow")
    if highlights:
        current_highlight_index = 0
        scroll_para_highlight(current_highlight_index)

def scroll_para_highlight(index):
    start, end = highlights[index]
    caixa_texto.see(start)
    caixa_texto.tag_remove("atual", "1.0", tk.END)
    caixa_texto.tag_add("atual", start, end)
    caixa_texto.tag_config("atual", background="orange")  # Destaque da ocorrência atual

def proximo_highlight():
    global current_highlight_index
    if not highlights:
        return
    current_highlight_index = (current_highlight_index + 1) % len(highlights)
    scroll_para_highlight(current_highlight_index)

def anterior_highlight():
    global current_highlight_index
    if not highlights:
        return
    current_highlight_index = (current_highlight_index - 1) % len(highlights)
    scroll_para_highlight(current_highlight_index)

# ================= Interface Tkinter =================
conteudo_completo = ""

janela = tk.Tk()
janela.title("Analisador de Logs Simples")
janela.geometry("1600x900")

btn_abrir = tk.Button(janela, text="Abrir Arquivo de Log", command=abrir_arquivo)
btn_abrir.pack(pady=5)

btn_limpar = tk.Button(janela, text="Limpar Caixa", command=limpar_caixa)
btn_limpar.pack(pady=5)

btn_exportar = tk.Button(janela, text="Exportar Exceções", command=exportar_excecoes)
btn_exportar.pack(pady=5)

label_arquivo = tk.Label(janela, text="Nenhum arquivo selecionado")
label_arquivo.pack(pady=5)

# Frame de busca
frame_busca = tk.Frame(janela)
frame_busca.pack(pady=5)
tk.Label(frame_busca, text="Buscar palavra-chave:").pack(side=tk.LEFT)
entry_busca = tk.Entry(frame_busca, width=30)
entry_busca.pack(side=tk.LEFT, padx=5)
btn_buscar = tk.Button(frame_busca, text="Buscar", command=buscar_palavra_chave)
btn_buscar.pack(side=tk.LEFT, padx=5)
btn_anterior = tk.Button(frame_busca, text="▲", command=anterior_highlight)
btn_anterior.pack(side=tk.LEFT, padx=2)
btn_proximo = tk.Button(frame_busca, text="▼", command=proximo_highlight)
btn_proximo.pack(side=tk.LEFT, padx=2)

# Caixa de texto
caixa_texto = scrolledtext.ScrolledText(janela, width=1600, height=900, state='disabled')
caixa_texto.pack(padx=10, pady=10)

janela.mainloop()
