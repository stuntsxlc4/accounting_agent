from accounting_agent import services

KSEF_NUMBER = "5261009190-20260808-554D64000000-F8"


class FakeClient:
    def __init__(self):
        self.calls = 0

    def get_invoice_xml(self, session, ksef_number):
        self.calls += 1
        return b"<Faktura/>"


def test_invoice_xml_is_downloaded_once(app_dirs):
    client = FakeClient()
    assert services.invoice_xml(client, None, KSEF_NUMBER) == b"<Faktura/>"
    assert services.invoice_xml(client, None, KSEF_NUMBER) == b"<Faktura/>"
    assert client.calls == 1


def test_invoice_xml_rejects_path_like_numbers(app_dirs):
    try:
        services.invoice_xml(FakeClient(), None, "../../etc/passwd")
    except ValueError:
        return
    raise AssertionError("niepoprawny numer KSeF został przyjęty")


def test_query_groups_fit_ksef_range_limit():
    months = [services._shift_month("2026-08", -i) for i in reversed(range(12))]
    groups = services._query_groups(months)
    assert [len(g) for g in groups] == [3, 3, 3, 3]
    for group in groups:
        start, _ = services.month_range(group[0])
        _, end = services.month_range(group[-1])
        assert (end - start).days < 100
