use atlas_violencia;

// Índices
// Regra ESR: Equality em seriesAnuais.ano + Sort em taxaHomicidiosPor100k.
db.municipios.createIndex({ codIBGE: 1 }, { name: "idx_codIBGE", unique: true });
db.municipios.createIndex({ nomeRegiao: 1 }, { name: "idx_nomeRegiao" });
db.municipios.createIndex({ "seriesAnuais.ano": 1 }, { name: "idx_series_ano" });
db.municipios.createIndex(
  { "seriesAnuais.ano": 1, "seriesAnuais.taxaHomicidiosPor100k": -1 },
  { name: "idx_esr_ano_taxa" }
);

// Q1 — Top 10 municípios com maior taxa de homicídios em 2022.
db.municipios.aggregate([
  { $unwind: "$seriesAnuais" },
  { $match: { "seriesAnuais.ano": 2022, "seriesAnuais.taxaHomicidiosPor100k": { $ne: null } } },
  { $sort: { "seriesAnuais.taxaHomicidiosPor100k": -1 } },
  { $limit: 10 },
  { $project: { _id: 0, municipio: "$nome", uf: "$siglaUF", regiao: "$nomeRegiao", taxa: "$seriesAnuais.taxaHomicidiosPor100k" } }
]);

// Q2 — Evolução de um município.
db.municipios.aggregate([
  { $match: { codIBGE: 2507507 } },
  { $project: {
      _id: 0,
      nome: 1,
      seriesAnuais: {
        $filter: {
          input: "$seriesAnuais",
          as: "s",
          cond: { $and: [ { $gte: ["$$s.ano", 2012] }, { $lte: ["$$s.ano", 2022] } ] }
        }
      }
  } }
]);

// Q3 — Média por região em 2022.
db.municipios.aggregate([
  { $unwind: "$seriesAnuais" },
  { $match: { "seriesAnuais.ano": 2022, "seriesAnuais.taxaHomicidiosPor100k": { $ne: null } } },
  { $group: { _id: "$nomeRegiao", mediaTaxa: { $avg: "$seriesAnuais.taxaHomicidiosPor100k" }, municipios: { $sum: 1 } } },
  { $sort: { mediaTaxa: -1 } }
]);

// Q4 — Violência x escolaridade.
db.municipios.aggregate([
  { $unwind: "$seriesAnuais" },
  { $match: { "seriesAnuais.ano": 2022, "seriesAnuais.taxaHomicidiosPor100k": { $ne: null }, "seriesAnuais.pctEnsinoMedioOuMais": { $ne: null } } },
  { $project: { _id: 0, municipio: "$nome", uf: "$siglaUF", taxa: "$seriesAnuais.taxaHomicidiosPor100k", escolaridade: "$seriesAnuais.pctEnsinoMedioOuMais" } }
]);

// Q5 — $elemMatch em array embutido.
db.municipios.find(
  { seriesAnuais: { $elemMatch: { taxaHomicidiosPor100k: { $gt: 50 }, pctEnsinoMedioOuMais: { $lt: 30 } } } },
  { _id: 0, codIBGE: 1, nome: 1, siglaUF: 1, "seriesAnuais.$": 1 }
);

// Q6 — Bucket por porte populacional.
db.municipios.aggregate([
  { $unwind: "$seriesAnuais" },
  { $match: { "seriesAnuais.ano": 2022, "seriesAnuais.populacaoTotal": { $ne: null } } },
  { $bucket: {
      groupBy: "$seriesAnuais.populacaoTotal",
      boundaries: [0, 20, 100, 999999],
      default: "Outro",
      output: { municipios: { $sum: 1 }, mediaTaxa: { $avg: "$seriesAnuais.taxaHomicidiosPor100k" } }
  } }
]);

// Q7 — Proveniência com $lookup.
db.municipios.aggregate([
  { $match: { codIBGE: 2507507 } },
  { $unwind: "$seriesAnuais" },
  { $match: { "seriesAnuais.ano": 2022 } },
  { $lookup: { from: "fontes", localField: "seriesAnuais.fonteIds", foreignField: "_id", as: "fontes" } },
  { $project: { _id: 0, municipio: "$nome", ano: "$seriesAnuais.ano", indicadores: "$seriesAnuais", "fontes.nome": 1, "fontes.portal": 1 } }
]);

// Explain Q1.
db.municipios.explain("executionStats").aggregate([
  { $unwind: "$seriesAnuais" },
  { $match: { "seriesAnuais.ano": 2022, "seriesAnuais.taxaHomicidiosPor100k": { $ne: null } } },
  { $sort: { "seriesAnuais.taxaHomicidiosPor100k": -1 } },
  { $limit: 10 }
]);
