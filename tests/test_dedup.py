from elbandito import dedup


def test_impronta_ignora_anno_ed_edizione_nel_titolo():
    a = dedup.impronta("Fondazione Mare Nostrum", "Premio Mare Nostrum 2027 – 3ª edizione", 2027)
    b = dedup.impronta("fondazione mare nostrum", "Premio Mare Nostrum", 2027)
    assert a == b
    assert a != dedup.impronta("Fondazione Mare Nostrum", "Premio Mare Nostrum", 2028)


def test_titoli_simili_dello_stesso_ente():
    ente = {"Ente": "Terna", "Titolo": "Premio Driving Energy 2026 – Fotografia Contemporanea"}
    stampa = {"Ente": "Terna S.p.A.", "Titolo": "Driving Energy 2026: premio di fotografia contemporanea"}
    altro = {"Ente": "Terna", "Titolo": "Bando borse di studio ingegneria"}
    assert dedup.simili(ente, stampa)
    assert not dedup.simili(ente, altro)


def test_trova_prima_impronta_poi_somiglianza():
    esistenti = [{"ID": "B0001", "Impronta": "abc", "Ente": "X", "Titolo": "Residenza Isole"}]
    assert dedup.trova({"Impronta": "abc", "Ente": "", "Titolo": ""}, esistenti)["ID"] == "B0001"
    assert dedup.trova({"Impronta": "zzz", "Ente": "X", "Titolo": "Residenza Isole 2027"}, esistenti)["ID"] == "B0001"
    assert dedup.trova({"Impronta": "zzz", "Ente": "Y", "Titolo": "Premio Città"}, esistenti) is None


def test_link_ufficiale_batte_aggregatore():
    assert dedup.link_migliore("https://www.exibart.com/x", "https://fondazione.it/bando") == "https://fondazione.it/bando"
    assert dedup.link_migliore("https://fondazione.it/bando", "https://www.exibart.com/x") == "https://fondazione.it/bando"


def test_unisci_fonti_senza_doppioni():
    assert dedup.unisci_fonti("F02, F04", "F04") == "F02, F04"
    assert dedup.unisci_fonti("", "F09") == "F09"
