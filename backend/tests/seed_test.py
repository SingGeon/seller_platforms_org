"""Demo data can be removed without touching real companies."""
from app import mongo
from app.seed import remove_demo
from app.scoring_service import recompute_scores


def test_remove_demo_keeps_registry_confirmed_companies(seeded):
    siemens = mongo.find_one(mongo.COMPANIES, {"domain": "siemens.com"})
    mongo.update_company(siemens.id, {"registry_profiles": {"wikidata": {"wikidata_id": "Q81230"}}})  # matched by a registry
    real = mongo.insert_company({"name": "Real Co", "domain": "real.example.org", "origin": "wikidata"})
    with seeded() as db:
        recompute_scores(db)
        stats = remove_demo(db)

    assert stats["demo_companies"] == 7 and stats["sample_documents"] > 0
    names = {c.name for c in mongo.find(mongo.COMPANIES)}
    assert names == {"Siemens", "Real Co"}
    assert mongo.db()[mongo.DOCUMENTS].count_documents({"meta.sample": True}) == 0
    assert {l.company_id for l in mongo.find(mongo.LEAD_SCORES)} == {siemens.id, real.id}
