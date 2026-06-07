# Projeto da Disciplina – Banco de Dados 2026.1
## Atlas da Violência × Indicadores Socioeconômicos por Município

**Equipe:** Rodrigo de Queiroz Gonçalves Velez · Caio Jordan de Lima Maia · Matheus Moreira Luna </br>
**Disciplina:** Banco de Dados — MPTI / IFPB (Campus João Pessoa) </br>
**Professor:** Diego Pessoa </br>
**Checkpoint:** C1 — Escopo + fonte + dicionário de dados (entrega 08/06/2026) </br>

---

## 2. Escopo (definição do problema)

### 2.a Problema de dados

A literatura em segurança pública sugere associação entre violência letal e fatores socioeconômicos (renda, educação, desigualdade), mas esses dados não convivem no mesmo ecossistema. Eles se encontram **separados**: o mapa da violência está localizado no Atlas da Violência (Ipea/FBSP) e os indicadores socioeconômicos estão no IBGE. Hoje, cruzar "taxa de homicídios" com "renda média" ou "escolaridade" de um mesmo município exige fazer download de planilhas distintas, padronizar nomes/códigos de município, à mão, e conciliar os períodos (anos).

A aplicação resolve isso oferecendo uma base **unificada e consultável** que responde, por município, região e ano, a perguntas como *"os municípios mais violentos são também os de menor renda/escolaridade?"* e *"como essa relação evoluiu na última década?"*.

**Usuários-alvo:**
- **Gestor público / formulador de políticas** (ex.: secretarias de segurança e de assistência social) que precisa priorizar territórios.
- **Pesquisador / jornalista de dados** que quer explorar a relação violência × condições socioeconômicas sem montar o pipeline do zero.

### 2.b Solução proposta

**Pipeline ETL (organização Medallion):**

```
* Bronze (JSON bruto por fonte/série)

Atlas da Violência (CSV local — Ipea)   ─┐
                                         ├─► [Extração]
IBGE SIDRA Tabela 5919 (CSV local)      ─┤
                                         │
IBGE API Localidades (REST — a coletar) ─┘

* Prata (JSON trabalhado)
                                            ↓
                              [Transformação] limpeza, type casting,
                              padronização do código IBGE do município (chave),
                              alinhamento de anos, cálculo de taxas,
                              agregação trimestral → anual (SIDRA),
                              junção município ↔ UF ↔ região (API Localidades)
                                            ↓
                              [Modelagem em documentos]
                              Município { dados fixos } + SériesAnuais[ { ano, indicadores } ]
                                            ↓
* Gold: carga no MongoDB
                                            ↓
                              Aplicação: mapa coroplético + ranking interativo
```

- **Extração:** leitura dos CSVs do Atlas (homicídios por município/sexo/ano) e do SIDRA (população por nível de instrução, trimestral, por município), além de chamada REST à API de Localidades do IBGE (catálogo de municípios com código, sigla da UF e nome da região), preservando o dado bruto na camada Bronze.
- **Transformação:** padronização da chave (código IBGE de 7 dígitos), conversão de tipos, deduplicação, junção das fontes por (município, ano) e construção dos documentos com array de séries anuais embutido.
- **Carga:** uma coleção `municipios` (uma entrada por município, com array `seriesAnuais`) e coleções de apoio (`regioes`/`ufs` e `fontes`) para exercitar referência + `$lookup`.

**Aplicação final:** dashboard web com:  
(1) **mapa coroplético** do Brasil por taxa de homicídios, com filtro de ano e indicador; 
(2) **ranking interativo** (top-N municípios) que cruza violência e indicador socioeconômico selecionado. Cada pergunta da Seção 4 vira um elemento da interface.

### 2.c Por que documentos/MongoDB (justificativa consciente)

O padrão de acesso dominante é *"pegar tudo de um município de uma vez"*: seus dados fixos mais toda a sua série histórica anual de violência e indicadores socioeconômicos — exatamente o que alimenta o mapa e o ranking. Modelar `Município` como documento com um **array embutido de séries anuais** mantém esses dados lidos-juntos fisicamente juntos, evitando o JOIN por ano que um PostgreSQL exigiria (uma tabela `municipio` + uma tabela `serie_anual` com 5–8 colunas e 1 linha por ano). Como a série por município é **limitada e de crescimento previsível** (cerca de uma entrada por ano, ~3 décadas → bem abaixo do limite de 16 MB do BSON), o embedding é seguro. O schema também tolera bem a **variação de indicadores entre anos/fontes** (campos opcionais ausentes em anos sem coleta), sem migração de esquema. Não é uma defesa absoluta — para análises estatísticas tabulares pesadas o relacional competiria —, mas para o padrão *"documento do município pronto para visualização"* o modelo de documentos serve melhor.

---

## 3. Entendimento da Fonte de Dados

O projeto usa **três fontes públicas e complementares**, unidas pelo **código IBGE do município** (chave de 7 dígitos comum às três). Duas já foram coletadas (arquivos locais); a terceira será consumida via API no pipeline ETL (C3).

### 3.a Fonte

---

#### Fonte 1 — Atlas da Violência / Ipea — *arquivos locais (já coletados)*

| Item | Descrição |
|---|---|
| Tipo | Arquivo CSV (download manual do portal Ipeadata) |
| Arquivos | `Homicídios Homens_municípios.csv` · `Homicídios Mulheres_municípios.csv` |
| Origem dos dados | Sistema de Informações sobre Mortalidade (SIM / Datasus / MS), elaboração Ipea / FBSP |
| Portal de acesso | `https://www.ipea.gov.br/atlasviolencia/` e `http://ipeadata.gov.br` |
| Acesso | Público, anônimo, sem chave de API; download direto dos arquivos |
| Licença / uso | Reprodução permitida **citando a fonte** (Ipea/FBSP); uso comercial proibido. Uso acadêmico não-comercial está coberto. |

Os dois arquivos têm estrutura idêntica: três colunas `Período, Região ID, Valor`, separadas por vírgula. `Período` é uma data ISO 8601 no formato `YYYY-01-15T00:00:00.000Z` (sempre 15 de janeiro; o ano é o dado útil). `Região ID` é o código IBGE de 7 dígitos do município. `Valor` é a contagem absoluta de homicídios no município/ano, desagregada por sexo conforme o arquivo.

---

#### Fonte 2 — IBGE / SIDRA — Tabela 5919 — *arquivo local (já coletado)*

| Item | Descrição |
|---|---|
| Tipo | Arquivo CSV (exportação via SIDRA / download manual) |
| Arquivo | `tabela5919-populacao-por-nivel-instrucao.csv` |
| Conteúdo | População residente (mil pessoas) por nível de instrução, por município e UF, trimestral |
| Cobertura temporal | 1º trimestre de 2012 → 4º trimestre de 2022 (44 trimestres) |
| Endpoint de origem (SIDRA v3) | `https://servicodados.ibge.gov.br/api/v3/agregados/5919/periodos/{periodo}/variaveis/606?localidades=N6[all]` |
| Documentação da API | `https://servicodados.ibge.gov.br/api/docs/agregados?versao=3` |
| Acesso | Público, anônimo; limite de ~100 mil registros por consulta na API |
| Licença / uso | Dados abertos IBGE; reprodução permitida **citando a fonte**; uso comercial da reprodução vedado. |

O arquivo é uma tabela **wide** (formato pivô): cada linha representa um município (prefixo `MU`) ou uma UF (prefixo `UF`); as colunas são o produto cartesiano trimestre × nível de instrução (9 níveis × 44 trimestres = 396 colunas de valores). Valores expressam **milhares de pessoas**; células com `"..."` indicam dado suprimido por imprecisão amostral. O pipeline ETL transformará esse formato para o modelo *long* (um registro por município/trimestre) antes de agregar anualmente.

---

#### Fonte 3 — IBGE API Localidades — *a coletar no pipeline ETL (C3)*

| Item | Descrição |
|---|---|
| Tipo | API REST — retorna JSON |
| Endpoint municípios | `https://servicodados.ibge.gov.br/api/v1/localidades/municipios` |
| Endpoint estados | `https://servicodados.ibge.gov.br/api/v1/localidades/estados` |
| Conteúdo | Catálogo completo de municípios brasileiros: código IBGE, nome, sigla e nome da UF, nome e sigla da região geográfica |
| Status | **Pendente de coleta** — será executada como primeira etapa da camada Bronze do pipeline ETL |
| Acesso | Público, anônimo, sem chave de API; sem limite documentado de requisições |
| Licença / uso | Dados abertos IBGE; mesmas condições da Fonte 2 |

Esta fonte fornece a **tabela de lookup geográfico** que une as demais: dado um `Região ID` de 7 dígitos presente nos CSVs do Atlas ou do SIDRA, a API retorna o nome do município, a sigla da UF (`"PB"`, `"SP"` …) e o nome da região (`"Nordeste"`, `"Sudeste"` …). Sem ela, não é possível montar o campo `regiao` do documento `municipio` nem filtrar/agregar por UF no dashboard.

> **Prévia do dado:** chamada `GET /api/v1/localidades/municipios` retorna um array JSON com ~5.570 objetos. Exemplo de um registro (simplificado):
> ```json
> {
>   "id": 2507507,
>   "nome": "João Pessoa",
>   "microrregiao": {
>     "mesorregiao": {
>       "UF": {
>         "id": 25,
>         "sigla": "PB",
>         "nome": "Paraíba",
>         "regiao": { "id": 2, "sigla": "NE", "nome": "Nordeste" }
>       }
>     }
>   }
> }
> ```

---

### 3.b Aspectos legais/éticos (LGPD)

**As três fontes NÃO contêm dados pessoais.**

Tanto o Atlas da Violência quanto o IBGE/SIDRA disponibilizam **dados agregados por território** (município, UF, região) e por ano — por exemplo, *número de homicídios no município X em 2022* e *população com ensino médio completo no município X*. A API de Localidades retorna apenas a taxonomia geográfica oficial. Não há identificadores individuais (nome, CPF, data de nascimento, endereço), e a granularidade municipal **não permite reidentificação** de pessoas. Os dados de mortalidade já são divulgados de forma estatística agregada pela fonte primária (SIM/MS) antes de chegarem ao Atlas.

Portanto, não há tratamento de dado pessoal a registrar à luz da LGPD. Ainda assim, a equipe adota como princípios: (i) **finalidade exclusivamente acadêmica**, sem decisão automatizada sobre indivíduos; (ii) **manutenção da granularidade agregada** (nunca tentar desagregar abaixo do município); e (iii) **citação obrigatória das fontes** (Ipea/FBSP e IBGE), conforme a licença.

---

### 3.c Metadados descritivos

| Atributo | Atlas — Homicídios Homens | Atlas — Homicídios Mulheres | SIDRA Tab. 5919 | IBGE Localidades |
|---|---|---|---|---|
| **Formato** | CSV (vírgula) | CSV (vírgula) | CSV (ponto-e-vírgula, wide) | JSON (REST) |
| **Volume** | 194.949 registros | 194.949 registros | 5.570 linhas MU + 27 UF × 396 colunas | ~5.570 objetos JSON |
| **Período / frequência** | 1989–2023, anual | 1989–2023, anual | 2012 Q1–2022 Q4, trimestral | Referência geográfica (atualizada no Censo) |
| **Cobertura territorial** | 5.580 municípios | 5.580 municípios | 5.570 municípios (PNAD Contínua) | 5.570 municípios |
| **Idioma** | PT-BR | PT-BR | PT-BR | PT-BR |
| **Encoding** | UTF-8 | UTF-8 | UTF-8 com BOM | UTF-8 |
| **Atualização** | Anual (último disponível: 2023) | Anual (último disponível: 2023) | Série encerrada em 2022 (¹) | Sob revisão censitária |
| **Unidade do valor** | Contagem absoluta de homicídios | Contagem absoluta de homicídios | Mil pessoas | — |
| **Chave de junção** | `Região ID` (código IBGE 7 dígitos) | `Região ID` (código IBGE 7 dígitos) | `Cód.` (código IBGE 7 dígitos) | `id` (código IBGE 7 dígitos) |

> (¹) A Tabela 5919 (nível de instrução total da população) foi descontinuada pelo IBGE a partir de agosto de 2025, conforme Nota Técnica 02/2025; a série histórica disponível vai até 4º trimestre de 2022. Para continuidade temporal, o pipeline poderá consultar as Tabelas 7128/7129 (módulo anual de Educação da PNAD Contínua) em versão futura.

---

### 3.d Dicionário de dados (metadados estruturais)

#### D1 — Atlas da Violência: `Homicídios Homens_municípios.csv` e `Homicídios Mulheres_municípios.csv`

> Estrutura idêntica nos dois arquivos; o sexo é diferenciado pelo nome do arquivo. Separador: vírgula. Cabeçalho na linha 1.

| Campo | Tipo (bruto) | Tipo (após ETL) | Descrição | Exemplo bruto | Exemplo transformado |
|---|---|---|---|---|---|
| `Período` | String | Integer (ano) | Data de referência anual no formato ISO 8601; sempre dia 15 de janeiro. O ETL extrai apenas o ano com 4 dígitos. | `1989-01-15T00:00:00.000Z` | `1989` |
| `Região ID` | Integer | Integer | Código IBGE do município (7 dígitos); chave de junção com SIDRA e API Localidades. Corresponde ao código de 6 dígitos + dígito verificador. | `1100015` | `1100015` |
| `Valor` | Integer | Integer | Contagem absoluta de homicídios registrados no município no ano de referência, para o sexo do arquivo. Valores `0` são registros válidos (ausência de ocorrências). | `11` | `11` |

**Observações:**
- O ETL gera, na camada Silver, um campo calculado `homicidiosTotais = homicídiosHomens + homicídiosMulheres` por (município, ano), além de `taxaHomicidiosPor100k` = `(homicídiosTotais / populacaoTotal) × 100.000` — usando a população da Fonte 2.
- Municípios com `Valor = 0` em todos os anos são retidos; municípios inexistentes em um dado ano (criados ou extintos) terão o ano ausente no array `seriesAnuais`.

---

#### D2 — IBGE SIDRA: `tabela5919-populacao-por-nivel-instrucao.csv`

> Arquivo exportado pelo SIDRA em formato wide (pivô). Separador: ponto-e-vírgula. Cabeçalho multi-linha (linhas 1–5); dados a partir da linha 6. Valores em **mil pessoas**. Células com `"..."` = dado suprimido; `"-"` = dado não aplicável; `".."` = dado não disponível.

| Campo | Tipo (bruto) | Tipo (após ETL) | Descrição | Exemplo bruto |
|---|---|---|---|---|
| `Nível` | String | String (filtro) | Nível geográfico da linha: `"UF"` (estado) ou `"MU"` (município). O ETL mantém apenas linhas `"MU"`. | `"MU"` |
| `Cód.` | String | Integer | Código IBGE do território. Para `MU`: 7 dígitos (município). Para `UF`: 2 dígitos (estado). | `"1100015"` |
| `UF e Município` | String | String | Nome do município ou UF conforme o nível. Municípios vêm indentados com espaços; o ETL aplica `.strip()`. | `"  Alta Floresta D'Oeste"` |
| `[Trimestre] × Total` | String | Float \| null | População total residente no trimestre (mil pessoas). Células `"..."` → `null`. | `"40.7"` |
| `[Trimestre] × Sem instrução e menos de 1 ano` | String | Float \| null | Pop. sem instrução ou com menos de 1 ano de estudo (mil pessoas). | `"3.2"` |
| `[Trimestre] × Ensino fundamental incompleto ou equivalente` | String | Float \| null | Pop. com fundamental incompleto (mil pessoas). | `"12.5"` |
| `[Trimestre] × Ensino fundamental completo ou equivalente` | String | Float \| null | Pop. com fundamental completo (mil pessoas). | `"5.1"` |
| `[Trimestre] × Ensino médio incompleto ou equivalente` | String | Float \| null | Pop. com médio incompleto (mil pessoas). | `"4.8"` |
| `[Trimestre] × Ensino médio completo ou equivalente` | String | Float \| null | Pop. com médio completo (mil pessoas). | `"11.3"` |
| `[Trimestre] × Ensino superior incompleto ou equivalente` | String | Float \| null | Pop. com superior incompleto (mil pessoas). | `"2.0"` |
| `[Trimestre] × Ensino superior completo ou equivalente` | String | Float \| null | Pop. com superior completo (mil pessoas). | `"1.8"` |
| `[Trimestre] × Não determinado` | String | Float \| null | Pop. sem declaração de nível de instrução (mil pessoas). | `"0.0"` |

> **Transformação necessária (wide → long):** o arquivo tem 44 trimestres × 9 colunas de nível = 396 colunas de valor. O ETL faz o *unpivot* para o formato `(codIBGE, trimestre, nivelInstrucao, valorMilPessoas)`, depois agrega trimestralmente calculando a **média anual** (4 trimestres) por nível de instrução, gerando uma linha por `(codIBGE, ano)`. O campo derivado `pctEnsinoMedioOuMais` = (médio completo + superior incompleto + superior completo) / total × 100 é calculado na camada Silver como proxy de escolaridade para o cruzamento com homicídios.

---

#### D3 — IBGE API Localidades (prévia — coleta a ser realizada no C3)

> Endpoint: `GET https://servicodados.ibge.gov.br/api/v1/localidades/municipios`  
> Retorna array JSON. Sem paginação — retorna todos os ~5.570 municípios em uma única resposta (~2 MB).

| Campo JSON | Tipo | Descrição | Exemplo |
|---|---|---|---|
| `id` | Integer | Código IBGE do município — **7 dígitos**; chave primária de junção com as demais fontes | `2507507` |
| `nome` | String | Nome oficial do município conforme IBGE | `"João Pessoa"` |
| `microrregiao.id` | Integer | Código da microrregião geográfica | `25013` |
| `microrregiao.nome` | String | Nome da microrregião | `"João Pessoa"` |
| `microrregiao.mesorregiao.id` | Integer | Código da mesorregião geográfica | `2502` |
| `microrregiao.mesorregiao.nome` | String | Nome da mesorregião | `"Mata Paraibana"` |
| `microrregiao.mesorregiao.UF.id` | Integer | Código da UF (2 dígitos) | `25` |
| `microrregiao.mesorregiao.UF.sigla` | String | Sigla da UF (2 letras maiúsculas) | `"PB"` |
| `microrregiao.mesorregiao.UF.nome` | String | Nome completo da UF | `"Paraíba"` |
| `microrregiao.mesorregiao.UF.regiao.id` | Integer | Código da região geográfica (1–5) | `2` |
| `microrregiao.mesorregiao.UF.regiao.sigla` | String | Sigla da região (N / NE / CO / SE / S) | `"NE"` |
| `microrregiao.mesorregiao.UF.regiao.nome` | String | Nome da região geográfica | `"Nordeste"` |

> **Uso no pipeline:** após a coleta, o ETL gera uma coleção auxiliar `ufs` (referência) e enriquece cada documento `municipio` com os campos fixos `nomeUF`, `siglaUF`, `nomeRegiao` e `siglaRegiao`, extraídos desta fonte. O campo `id` desta API corresponde exatamente ao `Região ID` do Atlas e ao `Cód.` do SIDRA — é a chave de junção universal do projeto.

> **Endpoint de estados (complementar):** `GET https://servicodados.ibge.gov.br/api/v1/localidades/estados` retorna os 27 estados com `id`, `sigla`, `nome` e `regiao` — será usado para popular a coleção `ufs` no MongoDB.

---

## 4. Requisitos de dados (perguntas que a aplicação responde)

> 7 perguntas. Cada uma já indica a consulta MongoDB esperada (Seção 7) e o elemento visual (Seção 8). O conjunto cobre: filtros/projeção, acesso a array embutido (`seriesAnuais`), aggregation multi-estágio, `$lookup` e `$bucket`.

| # | Pergunta | Consulta MongoDB esperada | Visual |
|---|---|---|---|
| Q1 | Quais os 10 municípios com maior taxa de homicídios em um ano selecionado? | `$unwind seriesAnuais` → `$match {ano}` → `$sort {taxa:-1}` → `$limit 10` | Ranking + barras |
| Q2 | Como a taxa de homicídios de um município evoluiu ao longo do período? | `find` com projeção do array via dot notation / `$filter` em `seriesAnuais` | Gráfico de linha |
| Q3 | Como a taxa média de homicídios se distribui por região/UF num ano? | `$unwind` → `$match {ano}` → `$group {_id:"$regiao", media:$avg}` → `$sort` | Mapa coroplético |
| Q4 | Os municípios de maior violência são os de menor renda/escolaridade? (cruzamento) | `$unwind` → `$match {ano}` → `$project {taxa, rendaPerCapita, escolaridade}` | Scatter plot (interativo) |
| Q5 | Quais municípios tiveram, em algum ano, taxa de homicídios acima de X **e** renda abaixo de Y? | `$elemMatch` em `seriesAnuais` (filtro composto no array) | Lista/tabela filtrável |
| Q6 | Qual a média de homicídios por **porte populacional** (pequeno / médio / grande)? | `$unwind` → `$bucket` por `populacao` → `$avg` (aplica padrão **Bucket/Computed**) | Barras agrupadas |
| Q7 | Para os top-N municípios, qual o órgão/fonte dos dados de cada indicador? | `$lookup` de `seriesAnuais.fonteIds` → coleção `fontes` | Tabela com proveniência |

---
