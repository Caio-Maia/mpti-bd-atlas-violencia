# Projeto da Disciplina – Banco de Dados 2026.1
## Atlas da Violência × Indicadores Socioeconômicos por Município

**Equipe:** Rodrigo de Queiroz Gonçalves Velez · Caio Jordan de Lima Maia · Matheus Moreira Luna
**Disciplina:** Banco de Dados — MPTI / IFPB (Campus João Pessoa)
**Professor:** Diego Pessoa
**Checkpoint:** C1 — Escopo + fonte + dicionário de dados (entrega 08/06/2026)

---

## 2. Escopo (definição do problema)

### 2.a Problema de dados

A literatura em segurança pública sugere associação entre violência letal e fatores socioeconômicos (renda, educação, desigualdade), mas esses dados vivem **separados**: a violência está no Atlas da Violência (Ipea/FBSP) e os indicadores socioeconômicos estão no IBGE. Hoje, cruzar "taxa de homicídios" com "renda média" ou "escolaridade" de um mesmo município exige baixar planilhas distintas, padronizar nomes/códigos de município à mão e conciliar anos.

A aplicação resolve isso oferecendo uma base **unificada e consultável** que responde, por município, região e ano, a perguntas como *"os municípios mais violentos são também os de menor renda/escolaridade?"* e *"como essa relação evoluiu na última década?"*.

**Usuários-alvo:**
- **Gestor público / formulador de políticas** (ex.: secretarias de segurança e de assistência social) que precisa priorizar territórios.
- **Pesquisador / jornalista de dados** que quer explorar a relação violência × condições socioeconômicas sem montar o pipeline do zero.

### 2.b Solução proposta

**Pipeline ETL (organização Medallion):**

```
Atlas da Violência (API REST Ipea)  ─┐
                                     ├─► [Extração]  → Bronze (JSON bruto por fonte/série)
IBGE SIDRA (API de Agregados v3)    ─┘
                                            ↓
                              [Transformação] limpeza, type casting,
                              padronização do código IBGE do município (chave),
                              alinhamento de anos, cálculo de taxas
                                            ↓
                              [Modelagem em documentos]
                              Município { dados fixos } + SériesAnuais[ { ano, indicadores } ]
                                            ↓
                                   Gold → carga no MongoDB
                                            ↓
                              Aplicação: mapa coroplético + ranking interativo
```

- **Extração:** coleta via API do Atlas (séries de homicídios por município) e via API de Agregados do IBGE/SIDRA (população, renda, escolaridade por município), preservando o JSON bruto na camada Bronze.
- **Transformação:** padronização da chave (código IBGE de 7 dígitos), conversão de tipos, deduplicação, junção das duas fontes por (município, ano) e construção dos documentos com array de séries anuais embutido.
- **Carga:** uma coleção `municipios` (uma entrada por município, com array `seriesAnuais`) e coleções de apoio (`regioes`/`ufs` e `fontes`) para exercitar referência + `$lookup`.

**Aplicação final:** dashboard web com (1) **mapa coroplético** do Brasil por taxa de homicídios, com filtro de ano e indicador; e (2) **ranking interativo** (top-N municípios) que cruza violência e indicador socioeconômico selecionado. Cada pergunta da Seção 4 vira um elemento da interface.

### 2.c Por que documentos/MongoDB (justificativa consciente)

O padrão de acesso dominante é *"pegar tudo de um município de uma vez"*: seus dados fixos mais toda a sua série histórica anual de violência e indicadores socioeconômicos — exatamente o que alimenta o mapa e o ranking. Modelar `Município` como documento com um **array embutido de séries anuais** mantém esses dados lidos-juntos fisicamente juntos, evitando o JOIN por ano que um PostgreSQL exigiria (uma tabela `municipio` + uma tabela `serie_anual` com 5–8 colunas e 1 linha por ano). Como a série por município é **limitada e de crescimento previsível** (cerca de uma entrada por ano, ~3 décadas → bem abaixo do limite de 16 MB do BSON), o embedding é seguro. O schema também tolera bem a **variação de indicadores entre anos/fontes** (campos opcionais ausentes em anos sem coleta), sem migração de esquema. Não é uma defesa absoluta — para análises estatísticas tabulares pesadas o relacional competiria —, mas para o padrão *"documento do município pronto para visualização"* o modelo de documentos serve melhor.

---

## 3. Entendimento da Fonte de Dados

> O projeto usa **duas fontes públicas e complementares**, unidas pelo **código IBGE do município** (chave de 7 dígitos comum às duas).

### 3.a Fonte

**Fonte 1 — Atlas da Violência (Ipea / FBSP)**

| Item | Descrição |
|---|---|
| Tipo | API REST |
| Endpoint-base | `https://www.ipea.gov.br/dados-api/` |
| Acesso | público, anônimo, sem chave de API |
| Dado primário | Sistema de Informações sobre Mortalidade (SIM/MS) e polícias; elaboração Ipea/FBSP |
| Licença/uso | Reprodução do texto e dos dados permitida **desde que citada a fonte**; reprodução para fins comerciais é proibida. Uso acadêmico não-comercial está coberto. |

**Fonte 2 — IBGE / SIDRA (API de Agregados v3)**

| Item | Descrição |
|---|---|
| Tipo | API REST |
| Endpoint-base | TODO` |
| Documentação | `https://servicodados.ibge.gov.br/api/docs/agregados?versao=3` |
| Acesso | público, anônimo, sem chave de API; limite de ~100 mil registros por consulta |
| Licença/uso | Dados abertos do IBGE; reprodução permitida **citando a fonte**, vedado uso comercial da reprodução |

### 3.b Aspectos legais/éticos (LGPD)

**As duas fontes NÃO contêm dados pessoais.**

Tanto o Atlas da Violência quanto o IBGE/SIDRA disponibilizam **dados agregados por território** (município, UF, região) e por ano — por exemplo, *número/taxa de homicídios por 100 mil habitantes no município X em 2022* e *rendimento médio do município X*. Não há identificadores individuais (nome, CPF, data de nascimento, endereço), e a granularidade municipal **não permite reidentificação** de pessoas. Os dados de mortalidade já são divulgados de forma estatística agregada pela fonte primária (SIM/MS) antes de chegarem ao Atlas.

Portanto, não há tratamento de dado pessoal a registrar à luz da LGPD. Ainda assim, a equipe adota como princípios: (i) **finalidade exclusivamente acadêmica**, sem decisão automatizada sobre indivíduos; (ii) **manutenção da granularidade agregada** (nunca tentar desagregar abaixo do município); e (iii) **citação obrigatória das fontes** (Ipea/FBSP e IBGE), conforme a licença.

### 3.c Metadados descritivos

| Atributo | Atlas da Violência | IBGE / SIDRA |
|---|---|---|

### 3.d Dicionário de dados (metadados estruturais)


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