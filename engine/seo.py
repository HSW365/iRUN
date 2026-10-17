"""Search optimization for every post iRun makes.

Short-form discovery is search now: TikTok, Instagram and YouTube rank a video on the words in its caption,
its on-screen text and its voiceover, not on piles of hashtags. So every post gets:
  - a first caption line that is the exact phrase a buyer types into the search bar
  - a small, tight hashtag set per platform (Instagram allows 5 at most; TikTok ranks 3-5 relevant ones best)
    built from: 1 high-volume tag + niche buyer tags + 1 brand tag
  - on YouTube Shorts: a keyword-first title, #Shorts, up to 3 description hashtags, and 15 search tags

Each product can set its own "seo" block in products.json / accounts.json:
  "seo": {"search": "ai receptionist for small business",
          "tags": ["aireceptionist", "smallbusiness", "contractor", "missedcalls"],
          "brand": "calltwin",
          "keywords": ["ai receptionist", "answering service", ...]}
Anything not set falls back to the built-in map below, then to the script's own hashtags.
"""
import re

# Search phrases and tags researched per product: what the buyer actually types, plus the niche
# tags that buyers (not other marketers) follow. Brand tag last.
DEFAULTS = {
    "operator": {"search": "AI that runs your small business marketing",
                 "tags": ["smallbusinesstips", "aitools", "businessautomation", "entrepreneur"], "brand": "irun",
                 "keywords": ["ai marketing tool", "ai for small business", "business automation", "ai business assistant",
                              "marketing automation", "social media automation", "ai website builder",
                              "small business marketing", "solo founder", "ai employee"]},
    "irun": {"search": "how to post every day on TikTok without editing",
             "tags": ["tiktokgrowth", "contentcreator", "socialmediamarketing", "aitools"], "brand": "irun",
             "keywords": ["tiktok growth", "post every day", "ai video maker", "faceless videos", "auto post tiktok",
                          "instagram reels automation", "content creation", "social media manager", "grow on tiktok"]},
    "klipit": {"search": "how to clip your Twitch and Kick streams",
               "tags": ["twitchclips", "streamer", "kickstreamer", "gta6"], "brand": "klipit",
               "keywords": ["twitch clips", "stream clipper", "kick clips", "auto clip stream", "streamer tips",
                            "how to grow on twitch", "vod to shorts", "gaming clips", "gta 6 clips"]},
    "calltwin": {"search": "AI receptionist for small business",
                 "tags": ["aireceptionist", "smallbusiness", "contractor", "missedcalls"], "brand": "calltwin",
                 "keywords": ["ai receptionist", "answering service", "missed calls", "virtual receptionist",
                              "contractor tips", "small business phone", "ai phone answering", "plumber business"]},
    "queenee": {"search": "how to get a website for your business",
                "tags": ["smallbusiness", "websitedesign", "blackownedbusiness", "entrepreneur"], "brand": "queenee",
                "keywords": ["business website", "website for small business", "website builder", "web design",
                             "artist website", "get a website", "online presence"]},
    "flipit": {"search": "how to analyze a house flip deal",
               "tags": ["realestateinvesting", "houseflipping", "wholesaling", "flippinghouses"], "brand": "flipit",
               "keywords": ["house flipping", "flip calculator", "real estate investing", "wholesaling real estate",
                            "deal analysis", "arv calculator", "fix and flip"]},
    "build-series": {"search": "how to build an app by yourself with AI",
                     "tags": ["buildinpublic", "solofounder", "entrepreneur", "aiapps"], "brand": "hsw365",
                     "keywords": ["build an app with ai", "solo founder", "one person business", "start a business",
                                  "veteran entrepreneur", "build in public", "no code"]},
    "friendy": {"search": "someone to talk to at night",
                "tags": ["overthinking", "selfgrowth", "mentalhealthawareness", "latenight"], "brand": "friendy",
                "keywords": ["someone to talk to", "ai friend", "can't sleep", "overthinking at night",
                             "lonely at night", "talk to someone", "ai companion app"]},
    "studio": {"search": "how to record vocals at home over a beat",
               "tags": ["homestudio", "independentartist", "rapper", "musicproducer"], "brand": "hsw365studio",
               "keywords": ["record vocals at home", "home studio", "free vocal recording", "how to mix vocals",
                            "autotune online", "independent artist", "recording studio online", "rap vocals"]},
    "speaking": {"search": "motivational speaker veteran",
                 "tags": ["motivation", "veteran", "motivationalspeaker", "mindset"], "brand": "hoodstar365",
                 "keywords": ["motivational speaker", "veteran speaker", "school speaker", "mindset",
                              "turn negative into positive", "army veteran story"]},
    "books": {"search": "books that change your mindset",
              "tags": ["booktok", "motivation", "veteran", "mindset"], "brand": "hoodstar365",
              "keywords": ["motivational books", "booktok", "memoir", "veteran author", "street to success story"]},
    "podcast": {"search": "real conversations about the hustle podcast",
                "tags": ["podcast", "hustle", "mindset", "entrepreneur"], "brand": "respectdagame",
                "keywords": ["hustle podcast", "street podcast", "motivational podcast", "entrepreneur podcast"]},
    "survivor": {"search": "one of one streetwear",
                 "tags": ["streetwear", "oneofone", "bleachedshirt", "veteranowned"], "brand": "hsw365",
                 "keywords": ["one of one shirt", "hand bleached shirt", "custom streetwear", "veteran owned brand"]},
    "prints": {"search": "streetwear art prints",
               "tags": ["artprint", "streetart", "wallart", "veteranowned"], "brand": "hsw365",
               "keywords": ["art prints", "giclee print", "wall art", "streetwear art"]},
    "faith": {"search": "faith over fear shirt",
              "tags": ["faithoverfear", "christianstreetwear", "streetwear", "faith"], "brand": "hsw365",
              "keywords": ["faith over fear", "christian shirt", "faith streetwear"]},
    "streetwear": {"search": "veteran owned streetwear brand",
                   "tags": ["streetwear", "veteranowned", "streetwearbrand", "ootd"], "brand": "hsw365",
                   "keywords": ["streetwear", "veteran owned", "hoodies", "graphic tees"]},
}

# New Ark Plumbing: local search is the whole game, so every tag carries the place.
LOCAL = {"newark": {"area": "nj", "tags": ["njplumber", "newjersey", "plumber", "homeowner"], "brand": "newarkplumbing"}}
LOCAL_SEARCH = {
    "emergency": "emergency plumber NJ", "heating": "furnace repair NJ", "waterheater": "water heater replacement NJ",
    "drain": "clogged drain plumber NJ", "plumbing": "plumber near me NJ", "geothermal": "geothermal installer NJ",
    "sprinklers": "fire sprinkler installation NJ",
}

LIMITS = {"instagram": 5, "tiktok": 5, "youtube": 3}


def _tag(t):
    return re.sub(r"[^a-z0-9_]", "", str(t).lower().lstrip("#"))


def profile(acct, product):
    """The SEO profile for a product: search phrase, ranked tags, brand tag, YouTube keywords."""
    pid = product.get("id", "")
    base = dict(DEFAULTS.get(pid, {}))
    if acct.get("id") in LOCAL:
        loc = LOCAL[acct["id"]]
        base = {"search": LOCAL_SEARCH.get(pid, f"{product.get('name', pid)} NJ"), "tags": loc["tags"],
                "brand": loc["brand"], "keywords": [LOCAL_SEARCH.get(pid, ""), "plumber nj", "nj plumbing",
                                                    "plumber near me", "heating repair nj"]}
    base.update(product.get("seo") or {})
    base.setdefault("search", product.get("name", ""))
    base.setdefault("tags", [])
    base.setdefault("brand", _tag(acct.get("handle", "")))
    base.setdefault("keywords", [])
    return base


def hashtags(acct, product, platform, script_tags=()):
    """Ranked, deduped hashtag list sized for the platform: niche buyer tags first, brand tag last."""
    p = profile(acct, product)
    limit = LIMITS.get(platform, 5)
    brand = _tag(p["brand"])
    pool = [_tag(t) for t in list(p["tags"]) + list(script_tags)]
    out = []
    for t in pool:
        if t and t != brand and t not in out and len(t) <= 30:
            out.append(t)
    out = out[: max(0, limit - 1)]
    if brand:
        out.append(brand)
    return out[:limit]


def caption(acct, product, platform, body, cta_line, script_tags=()):
    """Search phrase first, then the hook body, the call to action, then the hashtags."""
    p = profile(acct, product)
    search = p["search"].strip()
    body = (body or "").strip()
    lines = []
    if search and search.lower() not in body.lower():
        lines.append(search[0].upper() + search[1:])
    if body:
        lines.append(body)
    if cta_line and cta_line.lower()[:20] not in body.lower():
        lines.append(cta_line)
    tags = hashtags(acct, product, platform, script_tags)
    if platform == "youtube" and "shorts" not in tags:
        tags = (tags[:2] + ["shorts"])
    text = "\n\n".join(lines)
    if tags:
        text += "\n\n" + " ".join("#" + t for t in tags)
    return text, tags


def youtube_title(acct, product, hook):
    """Keyword-first Shorts title under 90 characters."""
    p = profile(acct, product)
    search = p["search"].strip()
    hook = (hook or "").strip().rstrip(".")
    title = f"{search[0].upper() + search[1:]} | {hook}" if search and hook else (search or hook)
    if len(title) > 85:
        title = (search or hook)[:85]
    return title + " #Shorts"


def youtube_tags(acct, product, script_tags=()):
    p = profile(acct, product)
    out = []
    for k in [p["search"]] + list(p["keywords"]) + [t for t in p["tags"]] + list(script_tags) + [p["brand"], acct.get("brand", "")]:
        k = str(k).strip().lower()
        if k and k not in out:
            out.append(k)
    return out[:15]
