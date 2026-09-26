from sales_pipeline.newstopics import classify, story_key, topic_queries
from sales_pipeline.sources.companies import mentions_strictly


def test_annex1_signals_are_recognised_in_romanian_german_and_english():
    assert classify("Atac cibernetic la Electrica. Compania precizează că nu sunt afectate sistemele") == ["security_incident"]
    assert classify("Banca lansează un program de eficientizare și reducerea costurilor") == ["cost_efficiency"]
    assert "automation_ai" in classify("Electrica lansează un sistem bazat pe inteligență artificială")
    assert "automation_ai" in classify("Das Unternehmen setzt auf KI und Automatisierung")
    assert "leadership_change" in classify("Ion Popescu a fost numit director de digitalizare")
    assert "shared_services" in classify("Grupul deschide un centru de servicii partajate la Cluj")
    assert "tech_partners" in classify("Compania a semnat un contract cu UiPath")
    assert "hiring_tech" in classify("Firma angajează 50 de programatori și analiști de date")
    assert classify("BASF plant Stellenabbau und Sparprogramm") == ["cost_efficiency", "layoffs_cuts"]


def test_news_without_a_need_or_change_has_no_topic():
    assert classify("CTP Cluj-Napoca a lansat astăzi site-ul oficial") == []
    assert classify("AnimaWings a transportat peste 500.000 de pasageri") == []


def test_same_story_from_two_outlets_has_one_key():
    assert story_key("Atac cibernetic la Electrica, sistemele nu sunt afectate - Europa Liberă") == story_key(
        "Atac cibernetic la Electrica, sistemele nu sunt afectate - Agerpres")


def test_topic_queries_follow_the_company_language():
    assert "digitalizare" in " ".join(topic_queries("MD"))
    assert "Digitalisierung" in " ".join(topic_queries("AT"))
    assert "automation" in " ".join(topic_queries("FR"))


def test_one_word_company_names_must_be_written_exactly():
    assert mentions_strictly("Electrica S.A.", "Atac cibernetic la Electrica")
    assert not mentions_strictly("Electrica S.A.", "O centrală electrică a fost oprită")
    assert mentions_strictly("Banca Transilvania S.A.", "banca transilvania anunta")
