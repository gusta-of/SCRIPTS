# Documentacao Completa - Analisador de Logs

## 1. Visao Geral

O **Analisador de Logs** e uma aplicacao desktop em Python (Tkinter) para identificar blocos de excecao/erro em arquivos de log, com:

- deteccao por palavras-chave configuraveis;
- contexto de linhas abaixo do ponto de falha;
- navegacao por cards de excecoes;
- busca textual com destaque e navegacao entre ocorrencias;
- gerenciamento de palavras-chave ativas, ignoradas e termos desconsiderados;
- exportacao do resultado completo ou apenas do bloco selecionado;
- distribuicao em `.exe` via PyInstaller.

Entrada principal: `analise.py`  
GUI principal: `ui/app.py`  
Core de analise: `core/log_analyzer.py`

## 2. Funcionalidades

### 2.1 Carregamento e validacao de log

- Seleciona arquivo via dialog (`Abrir Log`).
- Valida:
  - existencia/acesso;
  - se e arquivo (nao diretorio);
  - tamanho maximo (padrao: `50 MB`).

### 2.2 Extracao de blocos de excecao

- Palavras-chave padrao:
  - `Exception`, `Error`, `Traceback`, `CRITICAL`, `FATAL`
- Para cada linha que casa com keyword:
  - inclui a linha de hit;
  - inclui `N` linhas abaixo (`context`, padrao `30`).
- Faixas sobrepostas sao mescladas em um unico bloco.
- Cabecalho do bloco indica linha(s) de origem:
  - `[Linha X]` ou `[Linhas X, Y, Z]`.

### 2.3 Palavras desconsideradas (ignored terms)

- Termos em `ignored_terms` anulam hit apenas quando o match da keyword fica dentro do termo ignorado.
- Exemplo:
  - keyword: `Error`
  - ignored term: `ValueError`
  - `ValueError` sozinho nao gera bloco por `Error`.
  - `ValueError ... Error real` ainda gera bloco por `Error real`.

### 2.4 Interface e navegacao

- Cards com metricas:
  - arquivo;
  - quantidade de blocos;
  - ocorrencias da busca.
- Slider horizontal de blocos encontrados.
- Painel lateral com palavras encontradas e contagem.
- Busca por termo (case-insensitive) com:
  - destaque de todas as ocorrencias (`match`);
  - destaque da ocorrencia atual (`current`);
  - navegacao `Anterior/Proximo`, `F3`, `Shift+F3`.

### 2.5 Modal de pilha/contexto acima

- Acionado por card: `Ver pilha acima`.
- Mostra:
  - bloco atual numerado por linha real do arquivo;
  - linhas acima do bloco com quantidade configuravel (40..200).
- Campos de texto usam `wrap=tk.NONE` e agora possuem **scroll horizontal**, alem da vertical, para linhas longas.

### 2.6 Modal de palavras-chave

- Gerencia:
  - ativas;
  - ignoradas (desativadas);
  - palavras customizadas;
  - termos desconsiderados (`ignored_terms`).
- Layout responsivo dentro do proprio modal.
- Alteracoes exigem `RECARREGAR` para reprocessar arquivo aberto.

### 2.7 Exportacao

- `Exportar`: salva todo o conteudo analisado.
- `Exportar Bloco`: salva apenas o bloco atualmente selecionado.

## 3. Arquitetura do Projeto

## 3.1 Estrutura de pastas

```text
analisadorPython/
  analise.py
  AnalisadorLogs.spec
  core/
    __init__.py
    log_analyzer.py
  ui/
    __init__.py
    app.py
  tests/
    test_log_analyzer.py
  dist/
    AnalisadorLogs.exe
  build/
    ...
```

## 3.2 Camadas

- `core/`: regras de negocio de parsing e validacao de arquivo.
- `ui/`: apresentacao, eventos de interface, persistencia de preferencias e interacao com usuario.
- `tests/`: testes unitarios do core.
- `spec/dist/build`: empacotamento e artefatos de build.

## 4. Modulos e APIs Principais

## 4.1 `core/log_analyzer.py`

Constantes:

- `MAX_FILE_SIZE_MB = 50`
- `DEFAULT_CONTEXT = 30`
- `DEFAULT_NO_EXCEPTION_MESSAGE = "Nenhuma excecao encontrada no log."`
- `DEFAULT_SEPARATOR = "\n" + "-" * 72 + "\n"`
- `DEFAULT_KEYWORDS = ("Exception", "Error", "Traceback", "CRITICAL", "FATAL")`

Dataclass:

- `AnalysisResult`
  - `content: str`
  - `block_count: int`
  - `blocks: tuple[str, ...]`

Funcoes:

- `build_keyword_pattern(keywords)`:
  - remove vazios/espacos;
  - remove duplicados preservando ordem;
  - cria regex case-insensitive;
  - se lista vazia, retorna regex que nunca casa.
- `validate_input_path(path, max_file_size_mb=50)`:
  - retorna `(bool, mensagem_erro)`.
- `extract_exception_blocks(file_path, context, keywords, ignored_terms, pattern, separator)`:
  - le arquivo e delega para funcao baseada em linhas.
- `extract_exception_blocks_from_lines(lines, context, keywords, ignored_terms, pattern, separator)`:
  - identifica hits efetivos;
  - mescla ranges;
  - monta blocos com cabecalho de linha(s);
  - retorna `AnalysisResult`.

Interna:

- `_has_effective_keyword_match(line, keyword_pattern, ignored_pattern)`:
  - valida se existe ao menos um match de keyword fora dos spans ignorados.

## 4.2 `ui/app.py`

Classe principal:

- `LogAnalyzerApp(root: tk.Tk)`

Responsabilidades:

- construcao do layout principal;
- disparo de analise em thread (`_analyze_file_worker`);
- atualizacao da interface no thread principal (`root.after`);
- controle de estado da busca e selecao de blocos;
- modais (pilha/contexto e opcoes de keywords);
- persistencia de preferencias em JSON.

Persistencia local:

- arquivo: `%LOCALAPPDATA%/AnalisadorLogs/keywords.json`
- conteudo:
  - `custom_keywords`
  - `active_custom_keywords`
  - `ignored_terms`

Entry-point GUI:

- `main()` cria `tk.Tk()`, instancia app e executa `mainloop()`.

## 4.3 `core/__init__.py`

Reexporta API publica do core:

- `AnalysisResult`
- constantes principais
- funcoes de parsing/validacao.

## 4.4 `analise.py`

Ponto de entrada minimo:

- importa `main` de `ui.app`;
- executa `main()` quando rodado como script.

## 5. Fluxo de Execucao

1. Usuario abre um log (`open_file`).
2. App valida caminho/tamanho (`validate_input_path`).
3. App inicia thread de analise.
4. Thread le linhas e executa `extract_exception_blocks_from_lines`.
5. Resultado volta ao thread UI por `root.after`.
6. UI atualiza metricas/cards/painel lateral/texto.
7. Usuario navega blocos, busca termos, abre modal de pilha, exporta dados.

## 6. Concorrencia e Threading

- Parsing e leitura do arquivo ocorrem em `threading.Thread(daemon=True)` para nao travar UI.
- Alteracoes de widget Tkinter sempre no thread principal via `root.after`.

## 7. Atalhos de Teclado

- `Ctrl+O`: abrir arquivo
- `Ctrl+F`: focar busca (quando filtros visiveis)
- `F3`: proxima ocorrencia
- `Shift+F3`: ocorrencia anterior
- `Ctrl+S`: exportar resultado

## 8. Testes

Arquivo: `tests/test_log_analyzer.py`

Cobertura atual (core):

- extracao com contexto;
- inicio correto do bloco na linha de erro;
- merge de ranges sobrepostos;
- cenario sem matches;
- keywords customizadas e lista vazia;
- regras de ignored terms;
- regex case-insensitive;
- leitura por arquivo real temporario;
- validacao de caminho inexistente/diretorio/limite de tamanho.

Executar:

```powershell
py -m unittest -v
```

## 9. Execucao em Desenvolvimento

Pre-requisitos:

- Windows com Python 3.14+ (ou compativel com Tkinter + PyInstaller usado no projeto).

Comando:

```powershell
py analise.py
```

## 10. Build do Executavel (.exe)

Spec atual: `AnalisadorLogs.spec` (windowed, nome `AnalisadorLogs`, `upx=True`).

Instalacao PyInstaller:

```powershell
py -m pip install pyinstaller
```

Build usando spec:

```powershell
py -m PyInstaller AnalisadorLogs.spec
```

Saida:

- executavel: `dist/AnalisadorLogs.exe`
- artefatos intermediarios: `build/AnalisadorLogs/`

## 11. Tratamento de Erros

- Erros de validacao mostram `messagebox.showerror`.
- Erros durante analise em thread sao capturados e exibidos via `_on_analysis_error`.
- Falha de persistencia de preferencias nao interrompe app (falha silenciosa controlada).
- Exportacao trata `OSError` e informa ao usuario.

## 12. Limitacoes e Consideracoes

- Leitura completa do arquivo em memoria (`readlines`) pode impactar arquivos grandes.
- Limite padrao de 50MB reduz risco de uso excessivo.
- Busca e deteccao sao por substring simples/case-insensitive (nao tokeniza palavras).
- Projeto orientado a desktop Windows/Tkinter.

## 13. Melhorias Sugeridas

- suporte a processamento em streaming para logs maiores;
- perfis de filtros salvos por projeto/cliente;
- testes de interface (alem dos unitarios do core);
- opcao de exportar JSON/CSV;
- adicionar pipeline CI para testes e build automatizado.

## 14. Changelog Recente

- Modal de pilha atualizado para suportar rolagem horizontal em textos longos (linhas acima e bloco atual).

