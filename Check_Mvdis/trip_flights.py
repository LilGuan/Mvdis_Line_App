import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from config import TRIP_CURRENCY, TRIP_GUID, TRIP_GUID_SIG, TRIP_LOCALE


TRIP_FLIGHT_URL = "https://tw.trip.com/restapi/soa2/14566/FlightVarListQuery"
TRIP_FLIGHT_DETAIL_URL = "https://tw.trip.com/restapi/soa2/32001/FlightStatusDetail"

FLIGHT_REGIONS = [
    {"code": "tw", "name": "台灣"},
    {"code": "asia", "name": "亞洲"},
    {"code": "europe", "name": "歐洲"},
    {"code": "north_america", "name": "北美洲"},
    {"code": "oceania", "name": "大洋洲"},
    {"code": "middle_east", "name": "中東"},
]

FLIGHT_CITIES = [
    {"code": "TPE", "name": "桃園", "country": "台灣", "region": "tw", "home": True, "query_code": "TPE", "airport_code": "TPE"},
    {"code": "TSA", "name": "松山", "country": "台灣", "region": "tw", "home": True, "query_code": "TPE", "airport_code": "TSA"},
    {"code": "RMQ", "name": "台中", "country": "台灣", "region": "tw", "home": True},
    {"code": "CYI", "name": "嘉義", "country": "台灣", "region": "tw", "home": True},
    {"code": "TNN", "name": "台南", "country": "台灣", "region": "tw", "home": True},
    {"code": "KHH", "name": "高雄", "country": "台灣", "region": "tw", "home": True},
    {"code": "HUN", "name": "花蓮", "country": "台灣", "region": "tw", "home": True},
    {"code": "TTT", "name": "台東", "country": "台灣", "region": "tw", "home": True},
    {"code": "MZG", "name": "澎湖", "country": "台灣", "region": "tw", "home": True},
    {"code": "KNH", "name": "金門", "country": "台灣", "region": "tw", "home": True},
    {"code": "LZN", "name": "馬祖南竿", "country": "台灣", "region": "tw", "home": True},
    {"code": "MFK", "name": "馬祖北竿", "country": "台灣", "region": "tw", "home": True},
    {"code": "TYO", "name": "東京", "country": "日本", "region": "asia"},
    {"code": "OSA", "name": "大阪", "country": "日本", "region": "asia"},
    {"code": "OKA", "name": "沖繩", "country": "日本", "region": "asia"},
    {"code": "FUK", "name": "福岡", "country": "日本", "region": "asia"},
    {"code": "SEL", "name": "首爾", "country": "韓國", "region": "asia"},
    {"code": "PUS", "name": "釜山", "country": "韓國", "region": "asia"},
    {"code": "HKG", "name": "香港", "country": "香港", "region": "asia"},
    {"code": "BKK", "name": "曼谷", "country": "泰國", "region": "asia"},
    {"code": "SIN", "name": "新加坡", "country": "新加坡", "region": "asia"},
    {"code": "SHA", "name": "上海", "country": "中國", "region": "asia"},
    {"code": "BJS", "name": "北京", "country": "中國", "region": "asia"},
    {"code": "LON", "name": "倫敦", "country": "英國", "region": "europe"},
    {"code": "PAR", "name": "巴黎", "country": "法國", "region": "europe"},
    {"code": "ROM", "name": "羅馬", "country": "義大利", "region": "europe"},
    {"code": "MIL", "name": "米蘭", "country": "義大利", "region": "europe"},
    {"code": "AMS", "name": "阿姆斯特丹", "country": "荷蘭", "region": "europe"},
    {"code": "FRA", "name": "法蘭克福", "country": "德國", "region": "europe"},
    {"code": "MUC", "name": "慕尼黑", "country": "德國", "region": "europe"},
    {"code": "MAD", "name": "馬德里", "country": "西班牙", "region": "europe"},
    {"code": "BCN", "name": "巴塞隆納", "country": "西班牙", "region": "europe"},
    {"code": "NYC", "name": "紐約", "country": "美國", "region": "north_america"},
    {"code": "LAX", "name": "洛杉磯", "country": "美國", "region": "north_america"},
    {"code": "SFO", "name": "舊金山", "country": "美國", "region": "north_america"},
    {"code": "SEA", "name": "西雅圖", "country": "美國", "region": "north_america"},
    {"code": "YVR", "name": "溫哥華", "country": "加拿大", "region": "north_america"},
    {"code": "YYZ", "name": "多倫多", "country": "加拿大", "region": "north_america"},
    {"code": "SYD", "name": "雪梨", "country": "澳洲", "region": "oceania"},
    {"code": "MEL", "name": "墨爾本", "country": "澳洲", "region": "oceania"},
    {"code": "BNE", "name": "布里斯本", "country": "澳洲", "region": "oceania"},
    {"code": "AKL", "name": "奧克蘭", "country": "紐西蘭", "region": "oceania"},
    {"code": "DXB", "name": "杜拜", "country": "阿聯酋", "region": "middle_east"},
    {"code": "AUH", "name": "阿布達比", "country": "阿聯酋", "region": "middle_east"},
    {"code": "DOH", "name": "杜哈", "country": "卡達", "region": "middle_east"},
]


def get_region(region_code):
    return next((region for region in FLIGHT_REGIONS if region["code"] == region_code), None)


def get_city(city_code):
    return next((city for city in FLIGHT_CITIES if city["code"] == city_code), None)


def normalize_flight_no(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _flight_query_code(city_code):
    city = get_city(city_code)
    return (city or {}).get("query_code") or city_code


def _flight_airport_code(city_code):
    city = get_city(city_code)
    return (city or {}).get("airport_code")


def get_cities_by_region(region_code):
    cities = [city for city in FLIGHT_CITIES if city["region"] == region_code]
    return sorted(cities, key=lambda city: (not city.get("home"), city["country"], city["name"]))


def build_trip_headers(referer):
    cookie = (
        f"GUID={TRIP_GUID}; GUID.sig={TRIP_GUID_SIG}; "
        f"cookiePricesDisplayed={TRIP_CURRENCY}; ibu_h5_site=TW; "
        f"ibu_h5_group=trip; ibu_h5_local=zh-tw; ibu_h5_lang=zhtw; "
        f"ibu_h5_curr={TRIP_CURRENCY}"
    )
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://tw.trip.com",
        "referer": referer,
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "locale": TRIP_LOCALE,
        "currency": TRIP_CURRENCY,
        "x-ctx-country": "TW",
        "x-ctx-currency": TRIP_CURRENCY,
        "x-ctx-locale": TRIP_LOCALE,
        "cookie": cookie,
    }


def build_trace_url(base_url):
    timestamp_ms = int(time.time() * 1000)
    trace_id = f"{TRIP_GUID}-{timestamp_ms}-{random.randint(1000000, 9999999)}"
    return f"{base_url}?_fxpcqlniredt={TRIP_GUID}&x-traceID={trace_id}"


def trip_head():
    return {
        "cid": TRIP_GUID,
        "ctok": "",
        "cver": "1.0",
        "lang": "01",
        "sid": "8888",
        "syscode": "09",
        "auth": "",
        "xsid": "",
        "ClientID": TRIP_GUID,
        "Currency": TRIP_CURRENCY,
        "Language": "tw",
        "Locale": TRIP_LOCALE,
        "extension": [
            {"name": "i18n.locale", "value": "zh_TW"},
            {"name": "source", "value": "online"},
        ],
    }


def search_flights(depart_code, arrive_code, search_date, enrich_details=True):
    query_depart_code = _flight_query_code(depart_code)
    query_arrive_code = _flight_query_code(arrive_code)
    selected_depart_airport = _flight_airport_code(depart_code)
    selected_arrive_airport = _flight_airport_code(arrive_code)
    url = build_trace_url(TRIP_FLIGHT_URL)
    referer = (
        "https://tw.trip.com/actualtime/list.html"
        f"?departCity={query_depart_code}&arriveCity={query_arrive_code}"
        f"&departPort=&arrivePort=&date={search_date}&locale=zh_tw&origin=1"
    )
    payload = {
        "token": None,
        "dCode": query_depart_code,
        "aCode": query_arrive_code,
        "queryType": 2,
        "srchDate": search_date,
        "extparam": "",
        "head": trip_head(),
    }
    response = requests.post(url, headers=build_trip_headers(referer), json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    status = data.get("ResponseStatus", {})
    if status.get("Ack") != "Success":
        raise RuntimeError(f"Trip.com 查詢失敗: {status.get('Errors') or data.get('rtmsg') or 'Unknown error'}")
    flights = data.get("flst") or []
    flights = _filter_selected_airports(
        flights,
        selected_depart_airport,
        selected_arrive_airport,
    )
    if enrich_details:
        detail_depart_code = selected_depart_airport or query_depart_code
        detail_arrive_code = selected_arrive_airport or query_arrive_code
        flights = enrich_flight_details(flights, detail_depart_code, detail_arrive_code, search_date)
    return {
        "depart": get_city(depart_code) or {"code": depart_code, "name": depart_code, "country": ""},
        "arrive": get_city(arrive_code) or {"code": arrive_code, "name": arrive_code, "country": ""},
        "date": search_date,
        "flights": flights,
        "raw": data,
    }


def search_flights_by_number(flight_no, search_date=None, depart_code=None, arrive_code=None, allow_route_fallback=False):
    search_date = search_date or today_taipei_date()
    target_flight_no = normalize_flight_no(flight_no)
    if not target_flight_no:
        return _empty_flight_number_result(flight_no, search_date, depart_code, arrive_code)

    result = _search_flight_number_detail(target_flight_no, search_date, depart_code, arrive_code)
    if result.get("flights") or not allow_route_fallback:
        return result

    if depart_code and arrive_code:
        return _search_flight_number_from_route(target_flight_no, search_date, depart_code, arrive_code)

    for candidate_depart, candidate_arrive in _flight_number_candidate_routes():
        result = _search_flight_number_from_route(target_flight_no, search_date, candidate_depart, candidate_arrive)
        if result.get("flights"):
            return result
    return _empty_flight_number_result(target_flight_no, search_date, depart_code, arrive_code)


def _search_flight_number_from_route(flight_no, search_date, depart_code, arrive_code):
    try:
        result = search_flights(depart_code, arrive_code, search_date, enrich_details=False)
    except Exception as exc:
        print(f"⚠️ Trip.com flight route fallback failed {depart_code}->{arrive_code}: {exc}")
        return _empty_flight_number_result(flight_no, search_date, depart_code, arrive_code)

    route_matches = [
        item for item in result.get("flights", [])
        if normalize_flight_no(item.get("fno") or item.get("fltNo")) == flight_no
    ]
    if not route_matches:
        return _empty_flight_number_result(flight_no, search_date, depart_code, arrive_code)

    detail_depart_code = route_matches[0].get("dcode") or route_matches[0].get("dpcode") or _flight_query_code(depart_code)
    detail_arrive_code = route_matches[0].get("acode") or route_matches[0].get("apcode") or _flight_query_code(arrive_code)
    flights = enrich_flight_details(route_matches, detail_depart_code, detail_arrive_code, search_date)
    first_flight = flights[0].get("varItemInfo") or flights[0]
    return {
        "depart": _city_stub(
            first_flight.get("dpcode") or first_flight.get("dcode") or detail_depart_code,
            first_flight.get("dAirportShortName") or first_flight.get("dpname") or detail_depart_code,
        ),
        "arrive": _city_stub(
            first_flight.get("apcode") or first_flight.get("acode") or detail_arrive_code,
            first_flight.get("aAirportShortName") or first_flight.get("apname") or detail_arrive_code,
        ),
        "date": search_date,
        "flights": flights,
        "query_flight_no": flight_no,
    }


def _flight_number_candidate_routes():
    route_pairs = []

    def add_route(depart_code, arrive_code):
        if depart_code == arrive_code:
            return
        route = (depart_code, arrive_code)
        if route not in route_pairs:
            route_pairs.append(route)

    asia_codes = [city["code"] for city in FLIGHT_CITIES if city["region"] == "asia"]
    global_codes = [city["code"] for city in FLIGHT_CITIES if city["region"] != "tw"]
    taiwan_codes = [city["code"] for city in FLIGHT_CITIES if city["region"] == "tw"]

    for code in asia_codes:
        add_route("TPE", code)
        add_route(code, "TPE")
        add_route("TSA", code)
        add_route(code, "TSA")

    for code in taiwan_codes:
        add_route("TPE", code)
        add_route(code, "TPE")

    for code in ("TYO", "OSA", "OKA", "FUK", "SEL", "PUS", "HKG", "BKK", "SIN", "SHA", "BJS"):
        add_route("KHH", code)
        add_route(code, "KHH")

    for code in global_codes:
        add_route("TPE", code)
        add_route(code, "TPE")
        add_route("TSA", code)
        add_route(code, "TSA")

    return route_pairs[:90]


def _search_flight_number_detail(flight_no, search_date, depart_code=None, arrive_code=None):
    detail_depart_code = (_flight_airport_code(depart_code) or _flight_query_code(depart_code)) if depart_code else ""
    detail_arrive_code = (_flight_airport_code(arrive_code) or _flight_query_code(arrive_code)) if arrive_code else ""
    detail = get_flight_detail(flight_no, detail_depart_code, detail_arrive_code, search_date)
    detail_card = normalize_flight_detail(detail) or {}
    if not detail_card:
        return _empty_flight_number_result(flight_no, search_date, depart_code, arrive_code)
    if not _flight_detail_matches_search_date(detail_card, search_date):
        return _empty_flight_number_result(flight_no, search_date, depart_code, arrive_code)
    flight = {
        "fno": flight_no,
        "fltNo": detail_card.get("fltNo") or flight_no,
        "dcode": detail_card.get("dpcode") or detail_depart_code,
        "acode": detail_card.get("apcode") or detail_arrive_code,
        "detail": detail,
    }
    detail_card["fltNo"] = detail_card.get("fltNo") or flight_no
    flight["varItemInfo"] = detail_card
    return {
        "depart": get_city(depart_code) or _city_stub(detail_card.get("dpcode") or detail_depart_code, detail_card.get("dAirportShortName") or detail_depart_code),
        "arrive": get_city(arrive_code) or _city_stub(detail_card.get("apcode") or detail_arrive_code, detail_card.get("aAirportShortName") or detail_arrive_code),
        "date": search_date,
        "flights": [flight],
        "query_flight_no": flight_no,
    }


def _flight_detail_matches_search_date(flight, search_date):
    for key in ("dpDate", "deDate", "daDate"):
        value = flight.get(key)
        if not value:
            continue
        return str(value)[:10] == search_date
    return False


def _city_stub(code, name):
    city_name = str(name or code or "").split()[0]
    return {"code": code or city_name, "name": city_name or code or "-", "country": ""}


def _empty_flight_number_result(flight_no, search_date, depart_code=None, arrive_code=None):
    return {
        "depart": get_city(depart_code) or _city_stub(depart_code or "", "航班"),
        "arrive": get_city(arrive_code) or _city_stub(arrive_code or "", normalize_flight_no(flight_no)),
        "date": search_date,
        "flights": [],
        "query_flight_no": normalize_flight_no(flight_no),
    }


def _filter_selected_airports(flights, depart_airport=None, arrive_airport=None):
    if not depart_airport and not arrive_airport:
        return flights
    filtered = []
    for flight in flights:
        flight_depart = flight.get("dcode") or flight.get("dpcode")
        flight_arrive = flight.get("acode") or flight.get("apcode")
        if depart_airport and flight_depart != depart_airport:
            continue
        if arrive_airport and flight_arrive != arrive_airport:
            continue
        filtered.append(flight)
    return filtered


def enrich_flight_details(flights, depart_code, arrive_code, search_date):
    enriched = []
    for flight in flights:
        flight_no = flight.get("fno") or flight.get("fltNo")
        detail_depart = flight.get("dcode") or depart_code
        detail_arrive = flight.get("acode") or arrive_code
        if not flight_no:
            enriched.append(flight)
            continue
        try:
            detail = get_flight_detail(flight_no, detail_depart, detail_arrive, search_date)
            merged = dict(flight)
            merged["detail"] = detail
            detail_card = normalize_flight_detail(detail)
            if detail_card:
                merged["varItemInfo"] = detail_card
            enriched.append(merged)
        except Exception as exc:
            print(f"⚠️ Trip.com detail failed for {flight_no}: {exc}")
            enriched.append(flight)
    return enriched


def get_flight_detail(flight_no, depart_code, arrive_code, search_date):
    referer = (
        "https://tw.trip.com/actualtime/detail.html"
        f"?flightNo={flight_no}&departCity={depart_code}&arriveCity={arrive_code}"
        f"&date={search_date}&locale=zh_tw&origin=1"
    )
    payload = {
        "flightNo": flight_no,
        "departAirportCode": depart_code,
        "arrivalAirportCode": arrive_code,
        "departDateTime": f"{search_date} 00:00:00",
        "head": trip_head(),
    }
    response = requests.post(
        build_trace_url(TRIP_FLIGHT_DETAIL_URL),
        headers=build_trip_headers(referer),
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    status = data.get("ResponseStatus", {})
    if status.get("Ack") != "Success":
        raise RuntimeError(status.get("Errors") or data.get("serviceResult", {}).get("errorMessage") or "Unknown detail error")
    return data


def normalize_flight_detail(detail):
    top_info = detail.get("topInfo") or {}
    itinerary = top_info.get("itineraryInfo") or {}
    status_card = detail.get("flightStatusCard") or {}
    status_info = status_card.get("statusInfo") or {}
    flight_info = status_card.get("flightInfo") or {}
    depart_info = flight_info.get("departInfo") or {}
    arrival_info = flight_info.get("arrivalInfo") or {}
    if not depart_info and not arrival_info:
        return None
    return {
        "fltNo": itinerary.get("flightNo"),
        "airlineName": itinerary.get("airlineName"),
        "dpcode": depart_info.get("airportCode"),
        "apcode": arrival_info.get("airportCode"),
        "dAirportShortName": depart_info.get("airportShortName") or depart_info.get("shortName") or depart_info.get("airportName") or depart_info.get("name"),
        "aAirportShortName": arrival_info.get("airportShortName") or arrival_info.get("shortName") or arrival_info.get("airportName") or arrival_info.get("name"),
        "dTerminal": depart_info.get("terminal"),
        "aTerminal": arrival_info.get("terminal"),
        "dpDate": depart_info.get("plannedDateTime"),
        "deDate": depart_info.get("dateTime"),
        "daDate": depart_info.get("dateTime"),
        "apDate": arrival_info.get("plannedDateTime"),
        "aeDate": arrival_info.get("dateTime"),
        "aaDate": arrival_info.get("dateTime"),
        "srak": status_info.get("status"),
        "statusContent": status_info.get("content"),
    }


def today_taipei_date():
    return datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
