"""Offline tests for the growth engine. Run: python -m unittest discover tests"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "engine"))
import accounts  # noqa: E402
import ads  # noqa: E402
import carousel  # noqa: E402
import competitors  # noqa: E402
import insights  # noqa: E402
import planner  # noqa: E402
import shopify  # noqa: E402
import store_scan  # noqa: E402


def product(title, ptype, price, handle=None, compare=None, body="", tags=()):
    return {"id": abs(hash(title)), "title": title, "handle": handle or shopify.slug(title), "product_type": ptype,
            "vendor": "Acme", "tags": list(tags), "body_html": body,
            "variants": [{"price": str(price), "compare_at_price": compare, "available": True}]}


CATALOG = [
    product("Storm Hoodie", "Hoodies", 60, body="<p>Heavyweight fleece hoodie made for cold mornings. Cut and sewn in small runs.</p>", tags=["fleece", "winter"]),
    product("Night Hoodie", "Hoodies", 70, tags=["fleece"]),
    product("Logo Tee", "Tees", 30, compare="40.00", tags=["cotton"]),
    product("Blank Tee", "Tees", 20, tags=["cotton"]),
    product("Trail Cap", "Hats", 25),
]
META = {"title": "Acme Supply | Home", "site_name": "Acme Supply", "description": "Small-batch gear built to last."}


class Shopify(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(shopify.normalize("hsw365.co/collections/all"), "https://hsw365.co")
        self.assertEqual(shopify.account_id("https://www.hsw365.co"), "hsw365co")
        self.assertEqual(shopify.account_id("https://acme.myshopify.com"), "acme")
        for bad in ["", "localhost", "http://127.0.0.1", "https://intranet"]:
            with self.assertRaises(ValueError):
                shopify.normalize(bad)

    def test_summarize(self):
        c = shopify.summarize(CATALOG)
        self.assertEqual(c["products"], 5)
        self.assertEqual(c["price"], {"min": 20.0, "median": 30.0, "max": 70.0})
        self.assertEqual(c["types"]["Hoodies"], {"count": 2, "price": {"min": 60.0, "median": 65.0, "max": 70.0}})
        self.assertEqual(c["on_sale_pct"], 20)
        self.assertEqual(set(c["top_tags"][:2]), {"cotton", "fleece"})


class Scan(unittest.TestCase):
    def scan(self, products=CATALOG):
        with mock.patch.object(shopify, "fetch_products", return_value=products), \
             mock.patch.object(shopify, "fetch_meta", return_value=META):
            return store_scan.scan("acmesupply.com", use_ai=False)

    def test_profile(self):
        r = self.scan()
        a = r["account"]
        self.assertEqual((a["id"], a["brand"], a["enabled"], a["store"]), ("acmesupplycom", "Acme Supply", False, "https://acmesupply.com"))
        self.assertEqual([p["id"] for p in a["products"]], ["hoodies", "tees", "hats"])
        self.assertEqual(len({p["keyword"] for p in a["products"]}), 3)
        self.assertIn("Small-batch gear built to last.", a["voice"])
        for p in a["products"]:  # the repo rule: no prices in pitches
            self.assertNotIn("$", p["pitch"])
            self.assertEqual(p["cta"]["screen"][0], "SHOP ACMESUPPLY.COM")
        self.assertEqual(r["analysis"]["profile_source"], "catalog")

    def test_single_type_uses_products(self):
        r = self.scan([p for p in CATALOG if p["product_type"] == "Hoodies"])
        subs = r["account"]["products"]
        self.assertEqual(subs[0]["link"], "https://acmesupply.com/products/storm-hoodie")
        self.assertTrue(subs[0]["pitch"].startswith("Heavyweight fleece hoodie"))

    def test_ai_profile_merges(self):
        ai = {"voice": "Acme talks plain.", "audience": "Outdoor workers.",
              "subjects": [{"id": "hoodies", "audience": "cold-weather crews", "angles": ["built for 5am", "a", "b", "c"]}]}
        with mock.patch.object(shopify, "fetch_products", return_value=CATALOG), \
             mock.patch.object(shopify, "fetch_meta", return_value=META), \
             mock.patch.object(store_scan.writer, "ask_json", return_value=ai):
            r = store_scan.scan("acmesupply.com", use_ai=True)
        self.assertEqual(r["account"]["voice"], "Acme talks plain.")
        self.assertEqual(r["account"]["products"][0]["angles"], ["built for 5am", "a", "b"])
        self.assertEqual(r["analysis"]["profile_source"], "claude")

    def test_save_never_overwrites(self):
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, "accounts.json")
        with open(cfg, "w") as f:
            json.dump({"accounts": [{"id": "acmesupplycom", "brand": "Hand Written", "products": []}]}, f)
        r = self.scan()
        self.assertEqual(store_scan.save(r, cfg, d), "exists")
        with open(cfg) as f:
            kept = json.load(f)["accounts"]
        self.assertEqual((len(kept), kept[0]["brand"], kept[0]["store"]), (1, "Hand Written", "https://acmesupply.com"))
        r["account"]["id"] = r["analysis"]["account"] = "other"
        self.assertEqual(store_scan.save(r, cfg, d), "added")
        self.assertTrue(os.path.exists(os.path.join(d, "other-store.json")))


class Plan(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.patch = mock.patch.object(planner, "PLANS", self.dir)
        self.patch.start()
        self.acct = next(a for a in accounts.load() if a["id"] == "hsw365media")

    def tearDown(self):
        self.patch.stop()

    def test_thirty_days(self):
        plan = planner.refresh(self.acct, today=dt.date(2026, 10, 5))
        slots = plan["slots"]
        self.assertEqual(len(slots), 30 * 6)
        self.assertEqual((plan["start"], plan["end"]), ("2026-10-05", "2026-11-03"))
        day1 = [s for s in slots if s["date"] == "2026-10-05"]
        self.assertEqual([s["platform"] for s in day1].count("tiktok"), 4)
        a, b = [s for s in day1 if s["variant"]]
        self.assertEqual((a["variant"], b["variant"], a["product"], a["angle"]), ("A", "B", b["product"], b["angle"]))
        self.assertEqual(sum(1 for s in slots if s["variant"] == "A"), 15)
        ig = [s for s in slots if s["platform"] == "instagram"]
        self.assertEqual(sum(s["format"] == "carousel" for s in ig), 20)
        self.assertTrue(all(s["format"] == "video" for s in slots if s["platform"] == "tiktok"))
        used = {s["product"] for s in slots}
        self.assertEqual(used, {p["id"] for p in self.acct["products"]})
        self.assertEqual([slots[0]["phase"], slots[-1]["phase"]], ["introduce", "ask"])

    def test_weights_shift_share(self):
        plan = planner.refresh(self.acct, today=dt.date(2026, 10, 5), weights={"products": {"klipit": 2.0, "flipit": 0.5}})
        n = lambda pid: sum(1 for s in plan["slots"] if s["product"] == pid and s["variant"] != "B")
        self.assertGreater(n("klipit"), n("calltwin"))
        self.assertGreater(n("calltwin"), n("flipit"))
        self.assertGreater(n("flipit"), 0)

    def test_refresh_keeps_past_and_carries_rotation(self):
        first = planner.refresh(self.acct, today=dt.date(2026, 10, 5))
        again = planner.refresh(self.acct, today=dt.date(2026, 10, 8))
        self.assertEqual(again["start"], "2026-10-05")
        self.assertEqual(len(again["slots"]), 180)
        past = lambda p: [s for s in p["slots"] if s["date"] < "2026-10-08"]
        self.assertEqual(past(first), past(again))
        self.assertEqual(first["slots"], again["slots"])  # same weights -> same plan, not a restart from product 1
        new = planner.refresh(self.acct, today=dt.date(2026, 11, 20))
        self.assertEqual((new["start"], len(new["slots"])), ("2026-11-20", 180))

    def test_slot_for(self):
        planner.refresh(self.acct, today=dt.date(2026, 10, 5))
        s = planner.slot_for("hsw365media", dt.datetime(2026, 10, 5, 16, 20), "instagram")
        self.assertEqual((s["date"], s["hour_utc"]), ("2026-10-05", 15))
        late = planner.slot_for("hsw365media", dt.datetime(2026, 10, 6, 0, 30), "tiktok")  # late start of the 22:00 slot
        self.assertEqual((late["date"], late["hour_utc"]), ("2026-10-05", 22))
        self.assertIsNone(planner.slot_for("nobody", dt.datetime(2026, 10, 5, 16), "tiktok"))


class Insights(unittest.TestCase):
    NOW = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)

    def row(self, i, product, score_views, variant=None, exp=None, posted="2026-10-05T12:00:00Z", angle="a1"):
        m = {"views": score_views, "likes": 0, "comments": 0, "shares": 0, "saves": 0}
        return {"id": i, "account": "x", "platform": "tiktok", "product_id": product, "angle": angle, "format": "video",
                "experiment": exp, "variant": variant, "hook": f"hook {i}", "posted_at": posted, "metrics": m,
                "score": insights.score(m)}

    def test_score(self):
        self.assertEqual(insights.score({"views": 100, "likes": 10, "comments": 2, "shares": 1, "saves": 1}), 200)

    def test_summary_and_weights(self):
        rows = [self.row(1, "a", 400), self.row(2, "a", 600), self.row(3, "b", 100), self.row(4, "b", 100), self.row(5, "c", 900)]
        rep = insights.summarize("x", rows, self.NOW)
        self.assertEqual(rep["avg_score"], 420)
        self.assertEqual(rep["weights"]["products"], {"a": 1.19, "b": 0.5})  # c has one post: no weight yet
        self.assertEqual(rep["top_posts"][0]["hook"], "hook 5")
        self.assertEqual(rep["totals"]["views"], 2100)

    def test_experiments(self):
        rows = [self.row(1, "a", 300, "A", "t1"), self.row(2, "a", 500, "B", "t1"),
                self.row(3, "a", 30, "A", "t2"), self.row(4, "a", 50, "B", "t2"),
                self.row(5, "a", 900, "A", "t3", posted="2026-10-09T12:00:00Z"), self.row(6, "a", 100, "B", "t3", posted="2026-10-09T15:00:00Z"),
                self.row(7, "a", 100, "A", "t4")]
        res = {t["experiment"]: t for t in insights.experiments(rows, self.NOW)}
        self.assertEqual((res["t1"]["status"], res["t1"]["winner"]), ("settled", "B"))
        self.assertEqual(res["t2"]["status"], "not enough data")
        self.assertEqual(res["t3"]["status"], "running")
        self.assertEqual(res["t4"]["status"], "waiting for the second post")
        self.assertEqual(insights.summarize("x", rows, self.NOW)["winning_hooks"][0], "hook 2")

    def test_no_data(self):
        rep = insights.summarize("x", [], self.NOW)
        self.assertEqual((rep["weights"], rep["winning_hooks"], rep["avg_score"]), ({"products": {}, "angles": {}}, [], 0))


class Ads(unittest.TestCase):
    def test_moves_toward_winner_without_raising_total(self):
        sets = [{"id": "1", "daily_budget": 2000, "spend": 50, "roas": 4.0, "ctr": 1},
                {"id": "2", "daily_budget": 2000, "spend": 50, "roas": 1.0, "ctr": 3},
                {"id": "3", "daily_budget": 2000, "spend": 1, "roas": 9.0, "ctr": 9}]  # under min spend: untouched
        ch = {c["id"]: c for c in ads.rebalance(sets)}
        self.assertEqual(set(ch), {"1", "2"})
        self.assertEqual((ch["1"]["to"], ch["2"]["to"], ch["1"]["metric"]), (2400, 1600, "roas"))

    def test_falls_back_to_ctr_and_respects_floor(self):
        sets = [{"id": "1", "daily_budget": 110, "spend": 9, "roas": 0, "ctr": 0.0},
                {"id": "2", "daily_budget": 5000, "spend": 9, "roas": 0, "ctr": 2.5}]
        ch = {c["id"]: c for c in ads.rebalance(sets)}
        self.assertEqual(ch["1"]["to"], 100)
        self.assertEqual(ch["2"]["metric"], "ctr")
        self.assertLessEqual(ch["1"]["to"] + ch["2"]["to"], 5110)

    def test_total_never_rises(self):
        import random
        rnd = random.Random(7)
        for _ in range(500):
            sets = [{"id": str(i), "daily_budget": rnd.randint(100, 9000), "spend": rnd.choice([0, 6, 40]),
                     "roas": rnd.choice([0, 0, 1.5, 3]), "ctr": rnd.random() * 4} for i in range(rnd.randint(1, 7))]
            before = {s["id"]: s["daily_budget"] for s in sets}
            after = dict(before)
            for c in ads.rebalance(sets):
                self.assertGreaterEqual(c["to"], 100)
                self.assertLessEqual(abs(c["to"] - c["from"]), 0.2 * c["from"] + 1)
                after[c["id"]] = c["to"]
            self.assertLessEqual(sum(after.values()), sum(before.values()))

    def test_nothing_to_do(self):
        self.assertEqual(ads.rebalance([{"id": "1", "daily_budget": 2000, "spend": 50, "roas": 2, "ctr": 1}]), [])
        self.assertEqual(ads.rebalance([{"id": "1", "daily_budget": 2000, "spend": 50, "roas": 0, "ctr": 0},
                                        {"id": "2", "daily_budget": 2000, "spend": 50, "roas": 0, "ctr": 0}]), [])

    def test_dry_run_never_writes(self):
        acct = {"id": "t", "ads": {"campaign_ids": ["c1"]}}
        sets = [{"id": "1", "name": "a", "daily_budget": 2000, "spend": 50, "roas": 4.0, "ctr": 1},
                {"id": "2", "name": "b", "daily_budget": 2000, "spend": 50, "roas": 1.0, "ctr": 3}]
        d = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"META_ADS_TOKEN": "x"}), mock.patch.object(ads, "INTEL", d), \
             mock.patch.object(ads, "fetch_adsets", return_value=sets), mock.patch.object(ads.requests, "post") as post:
            os.environ.pop("IRUN_ADS_MODE", None)
            rep = ads.run(acct)
        post.assert_not_called()
        self.assertEqual((rep["mode"], len(rep["changes"])), ("dry-run", 2))


class Competitors(unittest.TestCase):
    def test_benchmark_and_changes(self):
        d = tempfile.mkdtemp()
        theirs = [product("Rival Hoodie", "Hoodies", 50), product("Rival Tee", "Tees", 30)]
        feeds = {"https://acmesupply.com": CATALOG, "https://rival.com": theirs}
        acct = {"id": "acme", "store": "https://acmesupply.com", "competitors": ["https://rival.com", "https://down.example.com"]}

        def fetch(base):
            if base not in feeds:
                raise RuntimeError("not a Shopify store")
            return feeds[base]

        with mock.patch.object(competitors, "INTEL", d):
            first = competitors.run(acct, fetch=fetch)
            self.assertEqual(first["changes"], [])
            rival = first["stores"][0]
            self.assertEqual(rival["vs_own"]["by_type"]["Hoodies"], {"own_median": 65.0, "their_median": 50.0, "own_vs_theirs_pct": 30})
            self.assertEqual(first["stores"][1]["readable"], False)
            feeds["https://rival.com"] = [product("Rival Hoodie", "Hoodies", 45), product("Rival Cap", "Hats", 20)]
            second = competitors.run(acct, fetch=fetch)
        kinds = sorted((c["change"], c["title"]) for c in second["changes"])
        self.assertEqual(kinds, [("new product", "Rival Cap"), ("price down", "Rival Hoodie"), ("removed", "Rival Tee")])


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class Engine(unittest.TestCase):
    """The real run.py path in draft mode with the voice stubbed (edge-tts needs the network)."""

    def fake_voice(self, text, out):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3", out], check=True)
        return out, 3.0, "test"

    def make(self, slot, platform):
        import run
        acct = next(a for a in accounts.load() if a["id"] == "hsw365co")
        prod = next(p for p in acct["products"] if p["id"] == "faith")
        script = {"beats": ["Fear told me to quit", "Faith told me to move", "One decision changes everything",
                            "Shop FAITH at hsw365.co"], "emphasis": ["quit", "move", "decision", "FAITH"],
                  "caption": "Faith over fear.", "hashtags": ["faith"]}
        out = tempfile.mkdtemp()
        with mock.patch.object(run.writer, "write_script", return_value=script) as ws, \
             mock.patch.object(run.voice, "speak", side_effect=self.fake_voice), \
             mock.patch.object(run.db, "enabled", return_value=False):
            row = run.make_one(acct, prod, platform, "draft", out, None, slot)
        return row, out, ws

    def test_carousel_slot(self):
        slot = {"product": "faith", "angle": "faith over fear, every day", "focus": "Introduce the brand.",
                "format": "carousel", "experiment": None, "variant": None}
        row, out, ws = self.make(slot, "instagram")
        self.assertEqual((row["format"], row["angle"], row["status"]), ("carousel", "faith over fear, every day", "draft"))
        self.assertEqual(ws.call_args.kwargs["fmt"], "carousel")
        self.assertEqual(ws.call_args.kwargs["focus"], "Introduce the brand.")
        jpgs = sorted(f for f in os.listdir(out) if f.endswith(".jpg"))
        self.assertEqual(len(jpgs), 4)
        from PIL import Image
        self.assertEqual(Image.open(os.path.join(out, jpgs[0])).size, (1080, 1350))

    def test_video_ab_slot(self):
        slot = {"product": "faith", "angle": "one decision changes everything", "focus": "x", "format": "video",
                "experiment": "hsw365co-20261005", "variant": "B"}
        row, out, _ = self.make(slot, "tiktok")
        self.assertEqual((row["format"], row["experiment"], row["variant"]), ("video", "hsw365co-20261005", "B"))
        self.assertEqual(len([f for f in os.listdir(out) if f.endswith(".mp4")]), 1)

    def test_carousel_never_goes_to_tiktok(self):
        slot = {"product": "faith", "angle": "a", "focus": "x", "format": "carousel", "experiment": None, "variant": None}
        row, _, _ = self.make(slot, "tiktok")
        self.assertEqual(row["format"], "video")

    def test_slide_text_fits(self):
        d = tempfile.mkdtemp()
        prod = {"name": "FOUNDER'S PRINT SERIES", "keyword": "PRINT"}
        paths = carousel.render_slides(["Supercalifragilistic extraordinarily long opening line for testing wraps", "Get the PRINT today"],
                                       ["", "PRINT"], prod, d, "t", cta=("SHOP HSW365.CO AND A VERY LONG LABEL HERE", "LIMITED: 25 EACH"))
        self.assertEqual(len(paths), 2)


if __name__ == "__main__":
    unittest.main()
