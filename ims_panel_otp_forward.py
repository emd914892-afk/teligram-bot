# ims_pannel_vps.py (FULL 24/7 VPS VERSION)
import time
import re
import os
import json
import logging
import tempfile
import traceback
from collections import deque
from datetime import datetime

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import requests

# Try importing webdriver_manager
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except Exception:
    WEBDRIVER_MANAGER_AVAILABLE = False

# Try importing phonenumbers
try:
    import phonenumbers
    PHONENUMBERS_AVAILABLE = True
except Exception:
    PHONENUMBERS_AVAILABLE = False

# ====================== কনফিগারেশন ======================
LOGIN_PAGE = "http://45.82.67.20/ints/client/SMSCDRStats"
OTP_PAGE =   "http://45.82.67.20/ints/client/SMSCDRStats"

# BOT TOKEN & GROUPS
CHEKER_BOT_TOKEN = "your api"
GROUP_CHAT_IDS = ["group id"]

USERNAME = "yourusername"
PASSWORD = "your pass"

# Poll & retry settings
POLL_INTERVAL_SECONDS = 15
MAX_LOGIN_RETRIES = 3

# OTP queue file (resolved to a writable folder at startup)
OTP_QUEUE_FILE = None

def resolve_otp_queue_file():
    """Find a writable path for otp_queue.json in the current running directory."""
    path = os.path.abspath("otp_queue.json")
    try:
        with open(path, "a", encoding="utf-8"):
            pass
        return path
    except OSError:
        return None

# cache size for seen messages
MAX_SEEN_CACHE = 20000

# ====================== সার্ভিস ও দেশ ম্যাপিং ======================
EXTENDED_SERVICES = {
    'whatsapp':'WhatsApp','telegram':'Telegram','facebook':'Facebook','facebook messenger':'Facebook Messenger',
    'messenger':'Facebook Messenger','google':'Google','gmail':'Gmail','google play':'Google Play','apple':'Apple',
    'itunes':'iTunes','app store':'App Store','instagram':'Instagram','twitter':'Twitter','x':'X',
    'amazon':'Amazon','microsoft':'Microsoft','outlook':'Outlook','live':'Microsoft','netflix':'Netflix',
    'bank':'Bank','banking':'Bank','hsbc':'HSBC','chase':'Chase','wells fargo':'Wells Fargo','citibank':'CitiBank',
    'paypal':'PayPal','stripe':'Stripe','binance':'Binance','coinbase':'Coinbase','kraken':'Kraken',
    'grab':'Grab','gojek':'Gojek','uber':'Uber','lyft':'Lyft','airbnb':'Airbnb','uber eats':'Uber Eats',
    'line':'Line','wechat':'WeChat','viber':'Viber','signal':'Signal','discord':'Discord','slack':'Slack',
    'linkedin':'LinkedIn','tumblr':'Tumblr','github':'GitHub','gitlab':'GitLab','dropbox':'Dropbox',
    'spotify':'Spotify','snapchat':'Snapchat','tiktok':'TikTok','okta':'Okta','adobe':'Adobe','yahoo':'Yahoo',
    'mtn':'MTN','vodafone':'Vodafone','safaricom':'Safaricom','imo':'Imo'
}

FALLBACK_COUNTRY_NAMES = {
    '98':'Iran','91':'India','1':'USA','44':'UK','86':'China','81':'Japan','82':'South Korea','65':'Singapore',
    '60':'Malaysia','63':'Philippines','84':'Vietnam','66':'Thailand','62':'Indonesia','92':'Pakistan','880':'Bangladesh',
    '93':'Afghanistan','94':'Sri Lanka','95':'Myanmar','975':'Bhutan','977':'Nepal','971':'UAE','966':'Saudi Arabia',
    '974':'Qatar','973':'Bahrain','968':'Oman','964':'Iraq','963':'Syria','962':'Jordan','961':'Lebanon','20':'Egypt',
    '90':'Turkey','967':'Yemen','221':'Senegal','222':'Mauritania','58':'Venezuela','260':'Zambia','233':'Ghana',
    '234':'Nigeria','27':'South Africa','351':'Portugal','33':'France','49':'Germany','39':'Italy','34':'Spain','7':'Russia',
    '52':'Mexico','54':'Argentina','55':'Brazil','61':'Australia','64':'New Zealand','47':'Norway','46':'Sweden','358':'Finland',
    '31':'Netherlands','380':'Ukraine'
}


# ====================== OTP Telegram format (app.py group style) ======================
DEFAULT_BUTTON_LINKS = {
    "group_link": "https://t.me/paidapjvarsonoph",
    "channel_link": "https://t.me/paidapjvarsonoph",
    "developer_link": "https://t.me/paidapjvarsonoph",
}
BUTTON_LINKS_FILE = "button_links.json"
IMS_GROUP_BOT_URL = "https://t.me/Unlimited_numberrakib_bot"

def load_button_links():
    if os.path.exists(BUTTON_LINKS_FILE):
        try:
            with open(BUTTON_LINKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_BUTTON_LINKS.copy()

SPECIAL_FLAGS = {
    "US": "<tg-emoji emoji-id='5976694588658686266'>🇺🇸</tg-emoji>",
    "RU": "<tg-emoji emoji-id='5294335323113807278'>🇷🇺</tg-emoji>",
    "EG": "<tg-emoji emoji-id='5222161185138292290'>🇪🇬</tg-emoji>",
    "ZA": "<tg-emoji emoji-id='5976697079739718234'>🇿🇦</tg-emoji>",
    "GR": "<tg-emoji emoji-id='5976335971774372579'>🇬🇷</tg-emoji>",
    "NL": "<tg-emoji emoji-id='5976438003017456076'>🇳🇱</tg-emoji>",
    "BE": "<tg-emoji emoji-id='5976300439509932178'>🇧🇪</tg-emoji>",
    "FR": "<tg-emoji emoji-id='5976706494308030299'>🇫🇷</tg-emoji>",
    "ES": "<tg-emoji emoji-id='5976424031488843687'>🇪🇸</tg-emoji>",
    "HU": "<tg-emoji emoji-id='5976789975587363092'>🇭🇺</tg-emoji>",
    "IT": "<tg-emoji emoji-id='5976298085867854649'>🇮🇹</tg-emoji>",
    "RO": "<tg-emoji emoji-id='5976646540859546652'>🇷🇴</tg-emoji>",
    "CH": "<tg-emoji emoji-id='5976561599291333244'>🇨🇭</tg-emoji>",
    "AT": "<tg-emoji emoji-id='5976586982548051976'>🇦🇹</tg-emoji>",
    "GB": "<tg-emoji emoji-id='5976531856642807659'>🇬🇧</tg-emoji>",
    "DK": "<tg-emoji emoji-id='5976380446160723453'>🇩🇰</tg-emoji>",
    "SE": "<tg-emoji emoji-id='5976775179425028923'>🇸🇪</tg-emoji>",
    "NO": "<tg-emoji emoji-id='5976327557933439693'>🇳🇴</tg-emoji>",
    "PL": "<tg-emoji emoji-id='5976482692152170488'>🇵🇱</tg-emoji>",
    "DE": "<tg-emoji emoji-id='5976493356555968244'>🇩🇪</tg-emoji>",
    "PE": "<tg-emoji emoji-id='5976420350701869282'>🇵🇪</tg-emoji>",
    "MX": "<tg-emoji emoji-id='5976658300480002579'>🇲🇽</tg-emoji>",
    "CU": "<tg-emoji emoji-id='5357035553508308603'>🇨🇺</tg-emoji>",
    "AR": "<tg-emoji emoji-id='5976803839741799351'>🇦🇷</tg-emoji>",
    "BR": "<tg-emoji emoji-id='5976287034917001256'>🇧🇷</tg-emoji>",
    "CL": "<tg-emoji emoji-id='5978610156957603801'>🇨🇱</tg-emoji>",
    "CO": "<tg-emoji emoji-id='5976555951409339416'>🇨🇴</tg-emoji>",
    "VE": "<tg-emoji emoji-id='5434009132753499322'>🇻🇪</tg-emoji>",
    "MY": "<tg-emoji emoji-id='5976838031976437927'>🇲🇾</tg-emoji>",
    "AU": "<tg-emoji emoji-id='5976552377996548545'>🇦🇺</tg-emoji>",
    "ID": "<tg-emoji emoji-id='5224405893960969756'>🇮🇩</tg-emoji>",
    "PH": "<tg-emoji emoji-id='5976772181537858123'>🇵🇭</tg-emoji>",
    "NZ": "<tg-emoji emoji-id='5976512722563503846'>🇳🇿</tg-emoji>",
    "SG": "<tg-emoji emoji-id='5976545437329399582'>🇸🇬</tg-emoji>",
    "TH": "<tg-emoji emoji-id='5976342573139106020'>🇹🇭</tg-emoji>",
    "JP": "<tg-emoji emoji-id='5976688764683033429'>🇯🇵</tg-emoji>",
    "KR": "<tg-emoji emoji-id='5976617773168597444'>🇰🇷</tg-emoji>",
    "VN": "<tg-emoji emoji-id='5976537109387810524'>🇻🇳</tg-emoji>",
    "CN": "<tg-emoji emoji-id='5976702693261975275'>🇨🇳</tg-emoji>",
    "TR": "<tg-emoji emoji-id='5976491638569048813'>🇹🇷</tg-emoji>",
    "IN": "<tg-emoji emoji-id='5976491823252642237'>🇮🇳</tg-emoji>",
    "PK": "<tg-emoji emoji-id='5976723210320748190'>🇵🇰</tg-emoji>",
    "AF": "<tg-emoji emoji-id='5976277263866403415'>🇦🇫</tg-emoji>",
    "LK": "<tg-emoji emoji-id='5976302702957697673'>🇱🇰</tg-emoji>",
    "MM": "<tg-emoji emoji-id='5188162778073935826'>🇲🇲</tg-emoji>",
    "IR": "<tg-emoji emoji-id='5976430585608935514'>🇮🇷</tg-emoji>",
    "MA": "<tg-emoji emoji-id='5224530035695693965'>🇲🇦</tg-emoji>",
    "DZ": "<tg-emoji emoji-id='5976325273010837563'>🇩🇿</tg-emoji>",
    "TN": "<tg-emoji emoji-id='5976645965333929511'>🇹🇳</tg-emoji>",
    "LY": "<tg-emoji emoji-id='5893101223564810175'>🇱🇾</tg-emoji>",
    "GM": "<tg-emoji emoji-id='5976483297742559352'>🇬🇲</tg-emoji>",
    "SN": "<tg-emoji emoji-id='5976483722944320690'>🇸🇳</tg-emoji>",
    "MR": "<tg-emoji emoji-id='5422465115360345921'>🇲🇷</tg-emoji>",
    "ML": "<tg-emoji emoji-id='5976768376196831695'>🇲🇱</tg-emoji>",
    "GN": "<tg-emoji emoji-id='5976350888195791241'>🇬🇳</tg-emoji>",
    "CI": "<tg-emoji emoji-id='5411283953984218884'>🇨🇮</tg-emoji>",
    "BF": "<tg-emoji emoji-id='5976557308619003946'>🇧🇫</tg-emoji>",
    "NE": "<tg-emoji emoji-id='5976647932428950438'>🇳🇪</tg-emoji>",
    "TG": "<tg-emoji emoji-id='5976576434108372678'>🇹🇬</tg-emoji>",
    "BJ": "<tg-emoji emoji-id='5976420385061608425'>🇧🇯</tg-emoji>",
    "MU": "<tg-emoji emoji-id='5976482670677333747'>🇲🇺</tg-emoji>",
    "LR": "<tg-emoji emoji-id='5976577718303595873'>🇱🇷</tg-emoji>",
    "SL": "<tg-emoji emoji-id='5976596925397342449'>🇸🇱</tg-emoji>",
    "GH": "<tg-emoji emoji-id='5976787188153588017'>🇬🇭</tg-emoji>",
    "NG": "<tg-emoji emoji-id='5976523777809323703'>🇳🇬</tg-emoji>",
    "TD": "<tg-emoji emoji-id='5979044524180117852'>🇹🇩</tg-emoji>",
    "CF": "<tg-emoji emoji-id='5976451437675156826'>🇨🇫</tg-emoji>",
    "CM": "<tg-emoji emoji-id='5976324706075154689'>🇨🇲</tg-emoji>",
    "CV": "<tg-emoji emoji-id='5976548697209575812'>🇨🇻</tg-emoji>",
    "ST": "<tg-emoji emoji-id='5976699343187482779'>🇸🇹</tg-emoji>",
    "GQ": "<tg-emoji emoji-id='5976814525620426462'>🇬🇶</tg-emoji>",
    "GA": "<tg-emoji emoji-id='5976396341834684925'>🇬🇦</tg-emoji>",
    "CG": "<tg-emoji emoji-id='5976332205088054604'>🇨🇬</tg-emoji>",
    "CD": "<tg-emoji emoji-id='5976337234494757335'>🇨🇩</tg-emoji>",
    "AO": "<tg-emoji emoji-id='5976833878743063435'>🇦🇴</tg-emoji>",
    "GW": "<tg-emoji emoji-id='5976526294660159661'>??🇼</tg-emoji>",
    "SC": "<tg-emoji emoji-id='5978929268732729465'>🇸🇨</tg-emoji>",
    "SD": "<tg-emoji emoji-id='5224372990216514135'>🇸🇩</tg-emoji>",
    "RW": "<tg-emoji emoji-id='5976558287871547862'>🇷🇼</tg-emoji>",
    "ET": "<tg-emoji emoji-id='5976492471792703601'>🇪🇹</tg-emoji>",
    "SO": "<tg-emoji emoji-id='5976732113787966649'>🇸🇴</tg-emoji>",
    "DJ": "<tg-emoji emoji-id='5976613946352736850'>🇩🇯</tg-emoji>",
    "KE": "<tg-emoji emoji-id='5976393060479669497'>🇰🇪</tg-emoji>",
    "TZ": "<tg-emoji emoji-id='5976297192514656545'>🇹🇿</tg-emoji>",
    "UG": "<tg-emoji emoji-id='5976539578994006362'>🇺🇬</tg-emoji>",
    "BI": "<tg-emoji emoji-id='5976742099586914503'>🇧🇮</tg-emoji>",
    "MZ": "<tg-emoji emoji-id='5976389130584594356'>🇲🇿</tg-emoji>",
    "ZM": "<tg-emoji emoji-id='5976750457593272380'>🇿🇲</tg-emoji>",
    "MG": "<tg-emoji emoji-id='5976827191478983649'>🇲🇬</tg-emoji>",
    "RE": "<tg-emoji emoji-id='5420322107068267129'>🇷🇪</tg-emoji>",
    "ZW": "<tg-emoji emoji-id='5976829738394589975'>🇿🇼</tg-emoji>",
    "NA": "<tg-emoji emoji-id='5976603874654426417'>🇳🇦</tg-emoji>",
    "MW": "<tg-emoji emoji-id='5341341330691863561'>🇲🇼</tg-emoji>",
    "LS": "<tg-emoji emoji-id='5976620972919232666'>🇱🇸</tg-emoji>",
    "BW": "<tg-emoji emoji-id='5976363541169445780'>🇧🇼</tg-emoji>",
    "SZ": "<tg-emoji emoji-id='5976741725924759442'>🇸🇿</tg-emoji>",
    "KM": "<tg-emoji emoji-id='5976698870741083962'>🇰🇲</tg-emoji>",
    "SH": "<tg-emoji emoji-id='5454076894997659542'>🇸🇭</tg-emoji>",
    "ER": "<tg-emoji emoji-id='5420548035232937623'>🇪🇷</tg-emoji>",
    "AW": "<tg-emoji emoji-id='5231044964212817289'>🇦🇼</tg-emoji>",
    "FO": "<tg-emoji emoji-id='5280985770188885026'>🇫🇴</tg-emoji>",
    "GL": "<tg-emoji emoji-id='5221969376193816323'>🇬🇱</tg-emoji>",
    "GI": "<tg-emoji emoji-id='5226496954623603888'>🇬🇮</tg-emoji>",
    "PT": "<tg-emoji emoji-id='5976327106961873123'>🇵🇹</tg-emoji>",
    "LU": "<tg-emoji emoji-id='5976285484433807436'>🇱🇺</tg-emoji>",
    "IE": "<tg-emoji emoji-id='5978894629821487879'>🇮🇪</tg-emoji>",
    "IS": "<tg-emoji emoji-id='5976698802021604508'>🇮🇸</tg-emoji>",
    "AL": "<tg-emoji emoji-id='5976498841229203219'>🇦🇱</tg-emoji>",
    "MT": "<tg-emoji emoji-id='5976479762984475758'>🇲🇹</tg-emoji>",
    "CY": "<tg-emoji emoji-id='5976803616403495510'>🇨🇾</tg-emoji>",
    "FI": "<tg-emoji emoji-id='5976510158468028132'>🇫🇮</tg-emoji>",
    "BG": "<tg-emoji emoji-id='5976616970009712457'>🇧🇬</tg-emoji>",
    "LT": "<tg-emoji emoji-id='5976837881652582376'>🇱🇹</tg-emoji>",
    "LV": "<tg-emoji emoji-id='5976740978600451694'>🇱🇻</tg-emoji>",
    "EE": "<tg-emoji emoji-id='5976277392715423938'>🇪🇪</tg-emoji>",
    "MD": "<tg-emoji emoji-id='5976792247625064355'>🇲🇩</tg-emoji>",
    "AM": "<tg-emoji emoji-id='5411455658186778270'>🇦🇲</tg-emoji>",
    "BY": "<tg-emoji emoji-id='5976363304946245889'>🇧🇾</tg-emoji>",
    "AD": "<tg-emoji emoji-id='5978725575613749734'>🇦🇩</tg-emoji>",
    "MC": "<tg-emoji emoji-id='5976425521842494767'>🇲🇨</tg-emoji>",
    "SM": "<tg-emoji emoji-id='5976790357839452073'>🇸🇲</tg-emoji>",
    "UA": "<tg-emoji emoji-id='5976654508023880370'>🇺🇦</tg-emoji>",
    "RS": "<tg-emoji emoji-id='5976463012612020480'>🇷🇸</tg-emoji>",
    "ME": "<tg-emoji emoji-id='5976333948844776590'>🇲🇪</tg-emoji>",
    "XK": "<tg-emoji emoji-id='5976633286590470030'>🇽🇰</tg-emoji>",
    "HR": "<tg-emoji emoji-id='5976744921380428432'>🇭🇷</tg-emoji>",
    "SI": "<tg-emoji emoji-id='5978926704637253502'>🇸🇮</tg-emoji>",
    "BA": "<tg-emoji emoji-id='5976670657100913091'>🇧🇦</tg-emoji>",
    "MK": "<tg-emoji emoji-id='5976441816948417573'>🇲🇰</tg-emoji>",
    "CZ": "<tg-emoji emoji-id='5976659369926859099'>🇨🇿</tg-emoji>",
    "SK": "<tg-emoji emoji-id='5976365662883290025'>🇸🇰</tg-emoji>",
    "LI": "<tg-emoji emoji-id='5976793342841725198'>🇱🇮</tg-emoji>",
    "FK": "<tg-emoji emoji-id='5454214681843481342'>🇫🇰</tg-emoji>",
    "BZ": "<tg-emoji emoji-id='5976828144961722583'>🇧🇿</tg-emoji>",
    "GT": "<tg-emoji emoji-id='5976766731224358097'>🇬🇹</tg-emoji>",
    "SV": "<tg-emoji emoji-id='5427301849831061043'>🇸🇻</tg-emoji>",
    "HN": "<tg-emoji emoji-id='5976504755399170515'>🇭🇳</tg-emoji>",
    "NI": "<tg-emoji emoji-id='5426842228200847679'>🇳🇮</tg-emoji>",
    "CR": "<tg-emoji emoji-id='5976659120818755766'>🇨🇷</tg-emoji>",
    "PA": "<tg-emoji emoji-id='5976690366705834196'>🇵🇦</tg-emoji>",
    "PM": "<tg-emoji emoji-id='5231258308123313128'>🇵🇲</tg-emoji>",
    "HT": "<tg-emoji emoji-id='5976439987292346381'>🇭🇹</tg-emoji>",
    "GP": "<tg-emoji emoji-id='5467664243081886165'>🇬🇵</tg-emoji>",
    "BO": "<tg-emoji emoji-id='5976750775420852685'>🇧🇴</tg-emoji>",
    "GY": "<tg-emoji emoji-id='5978986473402144429'>🇬🇾</tg-emoji>",
    "EC": "<tg-emoji emoji-id='5976442048876648469'>🇪🇨</tg-emoji>",
    "GF": "<tg-emoji emoji-id='5233523014313720667'>🇬🇫</tg-emoji>",
    "PY": "<tg-emoji emoji-id='5976609745874721028'>🇵🇾</tg-emoji>",
    "MQ": "<tg-emoji emoji-id='5976284878843418502'>🇲🇶</tg-emoji>",
    "SR": "<tg-emoji emoji-id='5976300113092417676'>🇸🇷</tg-emoji>",
    "UY": "<tg-emoji emoji-id='5976387133424803250'>🇺🇾</tg-emoji>",
    "CW": "<tg-emoji emoji-id='5233622988267472134'>🇨🇼</tg-emoji>",
    "TL": "<tg-emoji emoji-id='5422602597263489621'>🇹🇱</tg-emoji>",
    "AQ": "<tg-emoji emoji-id='5222477234601732139'>🇦🇶</tg-emoji>",
    "BN": "<tg-emoji emoji-id='5976686076033506746'>🇧🇳</tg-emoji>",
    "NR": "<tg-emoji emoji-id='5233464284930915439'>🇳🇷</tg-emoji>",
    "PG": "<tg-emoji emoji-id='5976504321607475018'>🇵🇬</tg-emoji>",
    "TO": "<tg-emoji emoji-id='5467490150877508877'>🇹🇴</tg-emoji>",
    "SB": "<tg-emoji emoji-id='5976631860661329134'>🇸🇧</tg-emoji>",
    "VU": "<tg-emoji emoji-id='5978614254356404774'>🇻🇺</tg-emoji>",
    "FJ": "<tg-emoji emoji-id='5978868701103920957'>🇫🇯</tg-emoji>",
    "PW": "<tg-emoji emoji-id='5976497857681693092'>🇵🇼</tg-emoji>",
    "WF": "<tg-emoji emoji-id='5231000034559934302'>🇼🇫</tg-emoji>",
    "CK": "<tg-emoji emoji-id='5454192094610473874'>🇨🇰</tg-emoji>",
    "NU": "<tg-emoji emoji-id='5454251094576218954'>🇳🇺</tg-emoji>",
    "WS": "<tg-emoji emoji-id='5976637886500444833'>🇼🇸</tg-emoji>",
    "KI": "<tg-emoji emoji-id='5976401719133739607'>🇰🇮</tg-emoji>",
    "NC": "<tg-emoji emoji-id='5233223766762338378'>🇳🇨</tg-emoji>",
    "TV": "<tg-emoji emoji-id='5454304115947487098'>🇹🇻</tg-emoji>",
    "PF": "<tg-emoji emoji-id='5467450310760874001'>🇵🇫</tg-emoji>",
    "TK": "<tg-emoji emoji-id='5231066898610798438'>🇹🇰</tg-emoji>",
    "FM": "<tg-emoji emoji-id='5976430375155538302'>🇫🇲</tg-emoji>",
    "MH": "<tg-emoji emoji-id='5976820856402222820'>🇲🇭</tg-emoji>",
    "KP": "<tg-emoji emoji-id='5341271404329317987'>🇰🇵</tg-emoji>",
    "HK": "<tg-emoji emoji-id='5222395857856374392'>🇭🇰</tg-emoji>",
    "MO": "<tg-emoji emoji-id='5420505321783179067'>🇲🇴</tg-emoji>",
    "KH": "<tg-emoji emoji-id='5976742700882335535'>🇰🇭</tg-emoji>",
    "LA": "<tg-emoji emoji-id='5976399640369568284'>🇱🇦</tg-emoji>",
    "BD": "<tg-emoji emoji-id='5976473818749737592'>🇧🇩</tg-emoji>",
    "TW": "<tg-emoji emoji-id='5222365101595568847'>🇹🇼</tg-emoji>",
    "MV": "<tg-emoji emoji-id='5976363386550622337'>🇲🇻</tg-emoji>",
    "LB": "<tg-emoji emoji-id='5976529279662430823'>🇱🇧</tg-emoji>",
    "JO": "<tg-emoji emoji-id='5976421677846764717'>🇯🇴</tg-emoji>",
    "SY": "<tg-emoji emoji-id='5308002793812955097'>🇸🇾</tg-emoji>",
    "IQ": "<tg-emoji emoji-id='5976458232313420307'>🇮🇶</tg-emoji>",
    "KW": "<tg-emoji emoji-id='5976679732366809576'>🇰🇼</tg-emoji>",
    "SA": "<tg-emoji emoji-id='5976726495970729818'>🇸🇦</tg-emoji>",
    "YE": "<tg-emoji emoji-id='5976685311529327157'>🇾🇪</tg-emoji>",
    "OM": "<tg-emoji emoji-id='5976284621145381432'>🇴🇲</tg-emoji>",
    "PS": "<tg-emoji emoji-id='5976410742860027765'>🇵🇸</tg-emoji>",
    "AE": "<tg-emoji emoji-id='5976594713489185156'>🇦🇪</tg-emoji>",
    "IL": "<tg-emoji emoji-id='5224720599099648709'>🇮🇱</tg-emoji>",
    "BH": "<tg-emoji emoji-id='5976668522502166844'>🇧??</tg-emoji>",
    "QA": "<tg-emoji emoji-id='5222225596762830469'>🇶🇦</tg-emoji>",
    "BT": "<tg-emoji emoji-id='5976318160544994744'>🇧🇹</tg-emoji>",
    "MN": "<tg-emoji emoji-id='5224192257992701543'>🇲🇳</tg-emoji>",
    "NP": "<tg-emoji emoji-id='5976563609336026965'>🇳🇵</tg-emoji>",
    "TJ": "<tg-emoji emoji-id='5976597573937404746'>🇹🇯</tg-emoji>",
    "TM": "<tg-emoji emoji-id='5978875276698851977'>🇹🇲</tg-emoji>",
    "AZ": "<tg-emoji emoji-id='5976582940983827573'>🇦🇿</tg-emoji>",
    "GE": "<tg-emoji emoji-id='5976431775314876794'>🇬🇪</tg-emoji>",
    "KG": "<tg-emoji emoji-id='5976533712068679686'>🇰🇬</tg-emoji>",
    "UZ": "<tg-emoji emoji-id='5976637328154696110'>🇺🇿</tg-emoji>",
    "KZ": "<tg-emoji emoji-id='5294227175837290463'>🇰🇿</tg-emoji>",
    "CA": "<tg-emoji emoji-id='5976694588658686266'>🇨🇦</tg-emoji>",
}

def get_flag(country_code):
    if not country_code:
        return "🌍"
    code = country_code.upper()
    if code in SPECIAL_FLAGS:
        return SPECIAL_FLAGS[code]
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))

def extract_tg_emoji_id(flag_str):
    m = re.search(r"emoji-id='(\d+)'", str(flag_str))
    return m.group(1) if m else None

def extract_plain_emoji(flag_str):
    m = re.search(r"<tg-emoji[^>]*>(.+?)</tg-emoji>", str(flag_str))
    if m:
        return m.group(1)
    return str(flag_str)

def detect_country_from_number(number, user_id=None):
    try:
        s = str(number).strip()
        if not s.startswith("+"):
            s = "+" + s
        if PHONENUMBERS_AVAILABLE:
            parsed = phonenumbers.parse(s, None)
            region = phonenumbers.region_code_for_number(parsed)
            if region:
                return get_country_name_from_iso(region), get_flag(region), region
        cleaned = re.sub(r"[^\d]", "", s).lstrip("+")
        for length in range(4, 0, -1):
            code = cleaned[:length]
            if code in FALLBACK_COUNTRY_NAMES:
                return FALLBACK_COUNTRY_NAMES[code], "🌍", code[:2].upper() if len(code) >= 2 else "UN"
    except Exception:
        pass
    return "Unknown", "🌍", "UN"

def detect_text_language(text):
    if not text:
        return "English"
    t = text.strip()
    if re.search(r"[\u0600-\u06FF]", t):
        return "Arabic"
    if re.search(r"[\u4e00-\u9fff]", t):
        return "Chinese"
    if re.search(r"[\u0900-\u097F]", t):
        return "Hindi"
    if re.search(r"[\u0400-\u04FF]", t):
        return "Russian"
    if re.search(r"[\u3040-\u30FF]", t):
        return "Japanese"
    if re.search(r"[\uAC00-\uD7AF]", t):
        return "Korean"
    if re.search(r"[\u0E00-\u0E7F]", t):
        return "Thai"
    if re.search(r"[\u1000-\u109F]", t):
        return "Burmese"
    tl = t.lower()
    if any(c in tl for c in ["ñ", "á", "é", "í", "ó", "ú", "¿"]):
        return "Spanish"
    if any(c in tl for c in ["à", "â", "ç", "è", "ê", "ë"]):
        return "French"
    if any(c in tl for c in ["ä", "ö", "ü", "ß"]):
        return "German"
    return "English"

SERVICE_MAP_OTP = {
    "whatsapp": ("WhatsApp", "5334998226636390258"),
    "telegram": ("Telegram", "5330237710655306682"),
    "facebook": ("Facebook", "5323261730283863478"),
    "instagram": ("Instagram", "5319160079465857105"),
    "tiktok": ("TikTok", "5327982530702359565"),
    "snapchat": ("Snapchat", "5330248916224983855"),
    "google": ("Google", "5303416490295304868"),
    "gmail": ("Google", "5303416490295304868"),
    "twitter": ("Twitter", "5330337435500951363"),
    "discord": ("Discord", "5325612636467903082"),
    "apple": ("Apple", "5947405256752107961"),
    "netflix": ("Netflix", "5318911503938634641"),
    "paypal": ("PayPal", "5364111181415996352"),
    "microsoft": ("Microsoft", "5334998226636390258"),
    "amazon": ("Amazon", "5334998226636390258"),
}

def mask_number_for_group(number):
    """
    গ্রুপ মেসেজ নম্বর মাস্ক: {country_code}xxx{শেষ ৩ ডিজিট}
    মাঝের সব ডিজিট লুকানো — যেকোনো দেশে একই নিয়ম।
    উদাহরণ: 8801712345678 -> 880xxx678 | 998931663703 -> 998xxx703
    """
    digits = re.sub(r"\D", "", str(number or ""))
    if not digits:
        return "xxx"

    country_code = None

    if PHONENUMBERS_AVAILABLE:
        try:
            parsed = phonenumbers.parse("+" + digits, None)
            country_code = str(parsed.country_code)
        except Exception:
            pass

    if not country_code:
        for length in range(4, 0, -1):
            prefix = digits[:length]
            if prefix in FALLBACK_COUNTRY_NAMES:
                country_code = prefix
                break

    if not country_code:
        if len(digits) > 10:
            country_code = digits[:3]
        elif len(digits) > 7:
            country_code = digits[:2]
        else:
            country_code = digits[:1]

    last_three = digits[-3:] if len(digits) >= 3 else digits
    return f"{country_code}xxx{last_three}"

def format_otp_message_v2(number, sms_text, service_name="[TG]", otp_code=None, is_group=False, user_lang=None, bot_uid=""):
    """Group OTP line format — same as app.py format_otp_message_v2(is_group=True)."""
    _country_name, flag, region_code = detect_country_from_number(number)
    lbl, eid = "Service", "5233354831984353090"
    for kw, (l, e) in SERVICE_MAP_OTP.items():
        if kw in (sms_text or "").lower():
            lbl, eid = l, e
            break
    else:
        raw = str(service_name).strip("[]").strip()
        if raw and not raw.startswith("<"):
            lbl = raw.upper()
        for kw, (l, e) in SERVICE_MAP_OTP.items():
            if kw in str(service_name).lower():
                lbl, eid = l, e
                break
    plain_flag = extract_plain_emoji(flag)
    flag_eid = extract_tg_emoji_id(flag)
    flag_display = f"<tg-emoji emoji-id='{flag_eid}'>{plain_flag}</tg-emoji>" if flag_eid else plain_flag
    if is_group:
        mlang_grp = detect_text_language(sms_text or "")
        masked_number = mask_number_for_group(number)
        return (
            f"↠ {flag_display} #{region_code} "
            f"<tg-emoji emoji-id='{eid}'>📱</tg-emoji> "
            f"<b>{masked_number}</b> #{mlang_grp} "
            f"┨<tg-emoji emoji-id='5282731554135615450'>🌩</tg-emoji>"
        )
    return ""

def create_group_otp_keyboard_markup(otp_code=None):
    """Inline keyboard — same layout as app.py create_group_otp_keyboard."""
    links = load_button_links()
    keyboard = []
    if otp_code and otp_code not in ("N/A", None, "----"):
        btn = {"text": f" {otp_code}", "copy_text": {"text": str(otp_code)}}
        try:
            btn["icon_custom_emoji_id"] = "5870972873450984431"
            btn["style"] = "primary"
        except Exception:
            pass
        keyboard.append([btn])
    channel_url = links.get("channel_link", "https://t.me/paidapjvarsonoph")
    keyboard.append([
        {"text": " Channel", "url": channel_url, "icon_custom_emoji_id": "5406809207947142040", "style": "danger"},
        {"text": " Number- Bot", "url": IMS_GROUP_BOT_URL, "icon_custom_emoji_id": "5244454921557789695", "style": "success"},
    ])
    return {"inline_keyboard": keyboard}

# --------------------- Logging ---------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --------------------- হেল্পারস ---------------------
def iso_country_to_flag(iso_code):
    if not iso_code or len(iso_code) != 2:
        return None
    try:
        base = 127397
        return chr(ord(iso_code[0].upper()) + base) + chr(ord(iso_code[1].upper()) + base)
    except Exception:
        return None

def get_country_name_from_iso(iso_code):
    if not iso_code: return "Unknown"
    mapping = {
        'BD':'Bangladesh','IN':'India','US':'United States','GB':'United Kingdom','CN':'China','JP':'Japan','KR':'South Korea',
        'SG':'Singapore','MY':'Malaysia','PH':'Philippines','VN':'Vietnam','TH':'Thailand','ID':'Indonesia','PK':'Pakistan',
        'AF':'Afghanistan','LK':'Sri Lanka','MM':'Myanmar','BT':'Bhutan','NP':'Nepal','AE':'UAE','SA':'Saudi Arabia','QA':'Qatar',
        'BH':'Bahrain','OM':'Oman','IQ':'Iraq','SY':'Syria','JO':'Jordan','LB':'Lebanon','EG':'Egypt','TR':'Turkey','YE':'Yemen',
        'SN':'Senegal','MR':'Mauritania','VE':'Venezuela','ZM':'Zambia','GH':'Ghana','NG':'Nigeria','ZA':'South Africa','PT':'Portugal',
        'FR':'France','DE':'Germany','IT':'Italy','ES':'Spain','RU':'Russia','MX':'Mexico','AR':'Argentina','BR':'Brazil','AU':'Australia',
        'NZ':'New Zealand','NO':'Norway','SE':'Sweden','FI':'Finland','NL':'Netherlands','UA':'Ukraine'
    }
    return mapping.get(iso_code.upper(), iso_code.upper())

def open_driver(headless=True):
    """
    Robust Edge WebDriver launcher for VPS.
    """
    edge_options = EdgeOptions()

    if headless:
        edge_options.add_argument("--headless")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("--disable-extensions")
        edge_options.add_argument("--disable-infobars")

    if WEBDRIVER_MANAGER_AVAILABLE:
        try:
            driver_path = EdgeChromiumDriverManager().install()
            service = EdgeService(executable_path=driver_path)
            driver = webdriver.Edge(service=service, options=edge_options)
            try: driver.set_page_load_timeout(120)
            except: pass
            try: driver.implicitly_wait(10)
            except: pass
            return driver
        except Exception as e:
            logging.warning("webdriver-manager failed: %s", e)

    # Fallback
    try:
        driver = webdriver.Edge(options=edge_options)
        try: driver.set_page_load_timeout(120)
        except: pass
        try: driver.implicitly_wait(10)
        except: pass
        return driver
    except Exception as e:
        logging.error("Failed to open Edge WebDriver: %s", e)
        raise

def try_find_element(driver, locators, timeout=10):
    for by, sel in locators:
        try:
            return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, sel)))
        except Exception:
            continue
    raise Exception(f"Element not found for any of: {locators}")

def send_telegram_message(chat_id: str, text: str, reply_markup: dict = None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"https://api.telegram.org/bot{CHEKER_BOT_TOKEN}/sendMessage", data=payload, timeout=15)
        if r.status_code == 200 and r.json().get('ok'):
            logging.info(f"✅ Message sent to {chat_id}")
            return r
        else:
            logging.warning("Telegram API returned %s: %s", r.status_code, r.text)
    except Exception as e:
        logging.warning("Exception sending to %s: %s", chat_id, e)
    return None

def _looks_like_sms_cell(text):
    if not text or len(text) < 4:
        return False
    t = text.lower()
    if re.search(r"\d{4,8}", text) or re.search(r"\d{3}[-\s]\d{3,4}", text):
        return True
    return any(k in t for k in (
        "code", "otp", "whatsapp", "telegram", "verification", "verify", "pin", "password", "код", "tiktok", "facebook", "google"
    ))

def _pick_sms_column(tds):
    texts = [td.get_text(" ", strip=True) for td in tds]
    
    # 1. Explicitly check for SMS patterns in columns 4 and beyond
    for t in texts[4:]:
        if _looks_like_sms_cell(t) and not t.startswith('$'):
            return t
            
    # 2. Default to index 4 if it's not a price
    if len(texts) > 4:
        if texts[4] and not texts[4].startswith('$'):
            return texts[4]
            
    # 3. Fallback to longest string that is not price
    candidates = [t for t in texts[4:] if not t.startswith('$') and t not in ('0', 'N/A')]
    if candidates:
        return max(candidates, key=len)
        
    return texts[4] if len(texts) > 4 else ""

def get_sms_rows(html: str):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    table = soup.find("table", {"id": "dt"})
    if not table:
        table = soup.find("table", class_=lambda c: c and "dataTable" in str(c))
    
    if not table:
        logging.warning("Debug: No table found with id 'dt' or class 'dataTable'")
        # Try to find ANY table as a fallback
        table = soup.find("table")
        if not table:
            logging.warning("Debug: No tables found on the page at all!")
            # Dump a small snippet of the page source for debugging
            snippet = str(html)[:500].replace('\n', ' ')
            logging.info("Debug: Page HTML snippet: " + snippet)
            return rows

    tbody = table.find("tbody")
    if not tbody:
        logging.warning("Debug: Table found but no <tbody> tag!")
        return rows
        
    trs = tbody.find_all("tr")
    logging.info(f"Debug: Found {len(trs)} <tr> elements in tbody.")
    
    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) < 5:
            logging.warning(f"Debug: Skipping row, only {len(tds)} <td> elements. Row text: {tr.get_text(strip=True)[:50]}")
            continue
        date = tds[0].get_text(strip=True)
        number = tds[2].get_text(strip=True)
        cli = tds[3].get_text(strip=True)
        sms = _pick_sms_column(tds)
        if number in ("0", "", "N/A") or sms in ("0", "", "N/A"):
            logging.warning(f"Debug: Skipping row, number or sms is empty. Number: {number}, SMS: {sms[:20]}")
            continue
        if not _looks_like_sms_cell(sms):
            logging.warning(f"Debug: Skipping row, doesn't look like SMS: {sms[:50]}")
            continue
        rows.append((date, number, cli, sms))
    return rows

def get_country_with_flag(number):
    if not number: return "🌐 Unknown Country"
    raw = str(number)
    num = re.sub(r'[^\d\+]', '', raw)
    if not num: return "🌐 Unknown Country"
    if num.startswith('00'): num = '+' + num[2:]
    elif not num.startswith('+'): num = '+' + num
    
    if PHONENUMBERS_AVAILABLE:
        try:
            parsed = phonenumbers.parse(num, None)
            region = phonenumbers.region_code_for_number(parsed)
            if region:
                flag = iso_country_to_flag(region) or '🌐'
                cname = get_country_name_from_iso(region)
                return f"{flag} {cname}"
        except Exception:
            pass
            
    cleaned = num.lstrip('+')
    for length in range(4, 0, -1):
        code = cleaned[:length]
        if code in FALLBACK_COUNTRY_NAMES:
            cname = FALLBACK_COUNTRY_NAMES[code]
            return f"🌐 {cname}"
    return "🌐 Unknown Country"

def detect_service(sms_text):
    if not sms_text: return "Unknown Service"
    text_lower = sms_text.lower()
    for k, v in EXTENDED_SERVICES.items():
        if re.search(r'\b' + re.escape(k) + r'\b', text_lower):
            return v
    for k, v in EXTENDED_SERVICES.items():
        if k in text_lower:
            return v
    return "Unknown Service"

def extract_otp(sms_text):
    if not sms_text:
        return None
    text = re.sub(r"[\r\n\t]+", " ", str(sms_text).strip())

    patterns = [
        r"(?:code|otp|pin|verification|verify|password)[^\d]{0,40}(\d{3,4}[-\s]\d{3,4})",
        r"(?:whatsapp|telegram|facebook|google|imo|viber)[^\d]{0,50}(\d{3,4}[-\s]\d{3,4})",
        r"(?<!\d)(\d{3}-\d{3,4})(?!\d)",
        r"(?<!\d)(\d{3,4}-\d{3,4})(?!\d)",
        r"(?<!\d)(\d{6})(?!\d)",
        r"(?<!\d)(\d{4,8})(?!\d)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            code = m.group(1).strip().replace(" ", "-")
            return code
    return None

def parse_simple_math(text):
    if not text: return None
    m = re.search(r'(-?\d+)\s*([\+\-\*/xX])\s*(-?\d+)', text)
    if not m: return None
    a = int(m.group(1)); op = m.group(2); b = int(m.group(3))
    try:
        if op == '+': return a + b
        if op == '-': return a - b
        if op in ['*', 'x', 'X']: return a * b
        if op == '/': return a // b
    except Exception:
        return None
    return None

def auto_login(driver, username, password):
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        try:
            driver.get(LOGIN_PAGE)
            time.sleep(1)
            username_el = try_find_element(driver, [(By.NAME, "username"), (By.ID, "username"), (By.NAME, "user"), (By.XPATH, "//input[@type='text']")], timeout=8)
            password_el = try_find_element(driver, [(By.NAME, "password"), (By.ID, "password"), (By.NAME, "pass"), (By.XPATH, "//input[@type='password']")], timeout=8)
            username_el.clear(); username_el.send_keys(username)
            password_el.clear(); password_el.send_keys(password)
            time.sleep(0.3)
            
            captcha_text = ""
            try:
                lbl = driver.find_element(By.XPATH, "//*[contains(text(),'What')]")
                captcha_text = lbl.text.strip()
            except Exception:
                pass
            
            if not captcha_text or not parse_simple_math(captcha_text):
                page_txt = driver.page_source or ""
                m = re.search(r'What\s*is\s*(\d+\s*[\+\-\*/xX]\s*\d+)', page_txt, re.IGNORECASE)
                if m: captcha_text = m.group(1)
            
            captcha_answer = parse_simple_math(captcha_text)
            if captcha_answer is not None:
                try:
                    captcha_input = try_find_element(driver, [(By.XPATH, "//input[@placeholder='Answer']"), (By.NAME, "answer"), (By.NAME, "captcha")], timeout=4)
                    captcha_input.clear(); captcha_input.send_keys(str(captcha_answer))
                    logging.info("Captcha auto-filled: %s", captcha_answer)
                except Exception as e:
                    logging.warning("Captcha input not found: %s", e)
            
            try:
                login_btn = try_find_element(driver, [(By.XPATH, "//button[contains(.,'Sign In') or contains(.,'Login')]") , (By.XPATH, "//input[@type='submit']"), (By.ID, "login_btn")], timeout=6)
                login_btn.click()
            except Exception:
                driver.execute_script("document.querySelectorAll('form')[0] && document.querySelectorAll('form')[0].submit();")
            
            time.sleep(30)
            driver.get(OTP_PAGE)
            logging.info("Auto-login done (attempt %d)", attempt)
            return True
        except Exception as e:
            logging.warning("Login attempt %d failed: %s", attempt, e)
            time.sleep(2)
    return False

def check_and_dismiss_alert(driver):
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        logging.warning("⚠️ Alert detected: %s", alert.text)
        alert.accept()
    except Exception:
        pass

def get_otp_page_html(driver, skip_refresh=False):
    check_and_dismiss_alert(driver)
    if not skip_refresh:
        try:
            driver.refresh()
        except Exception:
            check_and_dismiss_alert(driver)
            try: driver.get(OTP_PAGE)
            except: pass
    
    check_and_dismiss_alert(driver)
    time.sleep(5)
    return driver.page_source

def verify_write_path(path):
    if not path:
        return False
    try:
        folder = os.path.dirname(path) or "."
        os.makedirs(folder, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("")
        return True
    except Exception as e:
        logging.error("Cannot open/write OTP file %s: %s", path, e)
        return False

def save_otp(otp_data, path=None):
    path = path or OTP_QUEUE_FILE
    if not path:
        return False
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "a", encoding="utf-8", buffering=1) as f:
            json.dump(otp_data, f, ensure_ascii=False)
            f.write("\n")
            f.flush()
            try: os.fsync(f.fileno())
            except: pass
        return True
    except Exception as e:
        logging.warning("Save failed: %s", e)
        return False

# ====================== MAIN LOGIC (24/7 VPS READY) ======================
def main_loop(headless=True):
    global OTP_QUEUE_FILE
    if not OTP_QUEUE_FILE:
        OTP_QUEUE_FILE = resolve_otp_queue_file()
    if OTP_QUEUE_FILE and verify_write_path(OTP_QUEUE_FILE):
        logging.info("OTP queue file: %s", OTP_QUEUE_FILE)
    else:
        OTP_QUEUE_FILE = None
        logging.warning("OTP queue file disabled (no writable folder). Telegram forwarding will still run.")

    driver = None
    try:
        logging.info("🌐 Opening Browser (Headless: %s)...", headless)
        driver = open_driver(headless=headless)
        
        # Login
        if not auto_login(driver, USERNAME, PASSWORD):
            logging.error("❌ Login failed. Restarting browser cycle...")
            driver.quit()
            return

        # Caches
        sent_ids = deque(maxlen=MAX_SEEN_CACHE)
        sent_set = set()
        
        # Memory Management Counter
        loop_count = 0
        RESTART_THRESHOLD = 2000  # Restart browser after 2000 checks to free RAM

        logging.info("🚀 SMS forwarding started (24/7 Mode)")

        while True:
            # Check for memory leak prevention restart
            loop_count += 1
            if loop_count > RESTART_THRESHOLD:
                logging.info("🔄 Scheduled browser restart to clear memory...")
                break

            try:
                html = get_otp_page_html(driver, skip_refresh=(loop_count == 1))
                rows = get_sms_rows(html)
                
                logging.info(f"🔍 Found {len(rows)} SMS rows on page.")
                
                if not rows:
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                for date, number, cli, sms in rows:
                    signature = f"{date}|{number}|{sms[:40]}"
                    if signature in sent_set:
                        continue

                    otp_code = extract_otp(sms)
                    if not otp_code:
                        logging.warning("OTP not found in SMS (number=%s): %s", number, sms[:80])
                        continue
                    service_label = detect_service(sms) or cli
                    msg = format_otp_message_v2(number, sms, f"[{service_label}]", otp_code, is_group=True)
                    logging.info("📩 New SMS: %s | OTP: %s", number, otp_code)

                    inline_keyboard_markup = create_group_otp_keyboard_markup(otp_code)

                    for chat_id in GROUP_CHAT_IDS:
                        send_telegram_message(chat_id, msg, reply_markup=inline_keyboard_markup)

                    otp_data = {
                        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "source_time": date,
                        "number": number,
                        "otp": extract_otp(sms),
                        "service": detect_service(sms),
                        "raw": sms
                    }
                    save_otp(otp_data)

                    sent_ids.append(signature)
                    sent_set = set(sent_ids)

            except Exception as e:
                logging.error("⚠️ Error in main loop: %s", e)
                # Try to dismiss alert if that was the cause
                check_and_dismiss_alert(driver)
                
                # If driver is dead, break loop to trigger restart
                if "invalid session id" in str(e).lower() or "no such window" in str(e).lower():
                    break
                time.sleep(2)
            
            time.sleep(POLL_INTERVAL_SECONDS)

    except Exception as e:
        logging.error("🔥 Critical Browser Error: %s", e)
    finally:
        if driver:
            try:
                driver.quit()
                logging.info("🛑 Browser closed.")
            except Exception:
                pass

def run_forever():
    """
    Wrapper to keep the script running indefinitely on VPS.
    """
    logging.info("🔥 Starting 24/7 Monitor Script...")
    while True:
        try:
            # Force headless=True for VPS stability
            main_loop(headless=True)
        except KeyboardInterrupt:
            logging.info("User stopped the script.")
            break
        except Exception as e:
            logging.error("💥 Script crashed: %s", e)
        
        logging.info("♻️ Restarting script in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    run_forever()
