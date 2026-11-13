import re

import requests

from config import (
    BOLT_AUTHORIZATION,
    BOLT_BRAND,
    BOLT_COOKIE,
    BOLT_COUNTRY,
    BOLT_DEVICE_ID,
    BOLT_DEVICE_NAME,
    BOLT_DEVICE_OS_VERSION,
    BOLT_DEVICE_TYPE,
    BOLT_DISTINCT_ID,
    BOLT_LANGUAGE,
    BOLT_PAYMENT_METHOD_ID,
    BOLT_PAYMENT_METHOD_TYPE,
    BOLT_RH_SESSION_ID,
    BOLT_SESSION_ID,
    BOLT_USER_ID,
    BOLT_VERSION,
    TAIWANTAXI_ACCESS_TOKEN,
    TAIWANTAXI_ESTIMATE_URL,
    TAIWANTAXI_GIS_REVERSE_URL,
    TAIWANTAXI_GIS_SIGNATURE,
    TAIWANTAXI_GOOGLE_PLACE_DETAILS_URL,
    TAIWANTAXI_GOOGLE_PLACE_SIGNATURE,
    TAIWANTAXI_PREPARE_URL,
    TAIWANTAXI_SIGNATURE,
    TAIWANTAXI_TIME,
    TAIWANTAXI_USER_ID,
    TAXIGO_BILLING_TOKEN,
    TAXIGO_COOKIE,
    TAXIGO_TOKEN,
    UBER_COOKIE,
    UBER_COOKIE_CSID,
    UBER_COOKIE_SID,
    UBER_PAYMENT_PROFILE_UUID,
)


UBER_PRODUCTS_QUERY = """
query Products($destinations: [InputCoordinate!]!, $includeRecommended: Boolean = false, $payment: InputPayment, $paymentProfileUUID: String, $pickup: InputCoordinate!) {
  products(destinations: $destinations includeRecommended: $includeRecommended payment: $payment paymentProfileUUID: $paymentProfileUUID pickup: $pickup) {
    defaultVVID
    tiers {
      products {
        displayName
        isAvailable
        etaInMin
        productClassificationTypeName
        id
        fares {
          fare
          hasPromo
          discountPrimary
        }
      }
    }
  }
}
"""

TAXIGO_FIXED_FARE_LABELS = {
    "FIX_FARE": "LINE GO",
    "LOW_CARBON_FIX_FARE": "低碳",
    "LOW_CARBON_FIX_FARE_N7": "低碳",
    "LUXURY_FIX_FARE": "豪華",
    "SIX_PASSENGER_FIX_FARE": "六人座",
    "PET_FRIENDLY_FIX_FARE": "寵物車",
    "KID_SEAT_FIX_FARE": "兒童座椅",
    "WELCAB_FIX_FARE": "無障礙",
}

TAIWANTAXI_MODE_LABELS = {
    2001: "多元",
    2002: "豪華型多元",
    2003: "6 人座多元",
    2004: "寶寶多元",
}

TAIWANTAXI_KNOWN_ROUTES = {
    (25.056304, 121.548242): {
        "AddrId": "afx63x",
        "ProviderKey": "ChIJvZCKT82rQjQRRkXTOnyuKTU",
        "DisplayTitle": "",
        "Memo": "敦化北路168號",
        "Address": "台北市松山區No. 168號敦化北路",
        "Distance": 23,
        "Accuracy": 0,
        "Flag": 3,
        "City": "台北市",
        "Provider": 6,
    },
    (25.082673, 121.467255): {
        "AddrId": "aeu0ox",
        "ProviderKey": "1FLLNR",
        "DisplayTitle": "住家",
        "MemoForDriver": "",
        "Memo": "地球村",
        "Address": "新北市蘆洲區光華路108號",
        "Distance": 0,
        "Accuracy": 0,
        "Flag": 1,
        "City": "新北市",
        "Provider": 4,
    },
    (25.054855, 121.491321): {
        "AddrId": "adaaqx",
        "ProviderKey": "CRW2ZK",
        "DisplayTitle": "",
        "MemoForDriver": None,
        "Memo": "三重高中",
        "Address": "新北市三重區集美街212號",
        "Distance": 183694,
        "Accuracy": 0,
        "Flag": 3,
        "City": "新北市",
        "Provider": 4,
    },
}


def build_location(message):
    return {
        "title": message.title or "",
        "address": message.address or "",
        "latitude": message.latitude,
        "longitude": message.longitude,
    }


def compare_ride_fares(pickup, destination):
    results = []
    errors = []

    for provider_name, fetcher in (
        ("Uber", fetch_uber_quotes),
        ("LINE GO", fetch_taxigo_quotes),
        ("55688", fetch_taiwantaxi_quotes),
        ("Bolt", fetch_bolt_quotes),
    ):
        try:
            quotes = fetcher(pickup, destination)
            if quotes:
                results.append({"provider": provider_name, "quotes": quotes})
            else:
                errors.append(f"{provider_name}: 查無符合規則的固定價")
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")

    return {"pickup": pickup, "destination": destination, "results": results, "errors": errors}


def fetch_uber_quotes(pickup, destination):
    cookie = _uber_cookie()
    if not cookie:
        raise RuntimeError("缺少 UBER_COOKIE 或 UBER_COOKIE_SID/UBER_COOKIE_CSID")

    variables = {
        "includeRecommended": False,
        "destinations": [{"latitude": destination["latitude"], "longitude": destination["longitude"]}],
        "pickup": {"latitude": pickup["latitude"], "longitude": pickup["longitude"]},
    }
    if UBER_PAYMENT_PROFILE_UUID:
        variables["paymentProfileUUID"] = UBER_PAYMENT_PROFILE_UUID
        variables["payment"] = {
            "paymentProfileUUID": UBER_PAYMENT_PROFILE_UUID,
            "uberCashToggleOn": True,
        }

    response = requests.post(
        "https://m.uber.com/go/graphql",
        headers={
            "accept": "*/*",
            "content-type": "application/json",
            "cookie": cookie,
            "origin": "https://m.uber.com",
            "referer": "https://m.uber.com/go/product-selection",
            "x-csrf-token": "x",
            "user-agent": "Mozilla/5.0",
        },
        json={"operationName": "Products", "query": UBER_PRODUCTS_QUERY, "variables": variables},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        message = payload["errors"][0].get("message") or payload["errors"][0].get("extensions", {}).get("code")
        raise RuntimeError(message or "Uber API error")

    products = []
    for tier in payload.get("data", {}).get("products", {}).get("tiers", []):
        products.extend(tier.get("products") or [])

    quotes = []
    seen = set()
    for product in products:
        if not product.get("isAvailable"):
            continue
        fare_data = (product.get("fares") or [{}])[0]
        fare = fare_data.get("fare", "")
        if not _is_single_twd_price(fare):
            continue
        if fare_data.get("hasPromo") or fare_data.get("discountPrimary"):
            continue
        name = product.get("displayName") or "Uber"
        if name in seen:
            continue
        seen.add(name)
        quotes.append({
            "name": name,
            "fare": fare,
            "eta": _format_eta(product.get("etaInMin")),
        })

    return quotes


def fetch_taxigo_quotes(pickup, destination):
    cookie = _taxigo_cookie()
    if not cookie:
        raise RuntimeError("缺少 TAXIGO_COOKIE 或 TAXIGO_TOKEN")

    response = requests.post(
        "https://api.taxigo.com.tw/v2/rides/estimate",
        headers={
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "cookie": cookie,
            "origin": "https://app.taxigo.com.tw",
            "referer": "https://app.taxigo.com.tw/",
            "user-agent": "Mozilla/5.0",
        },
        json={
            "reservation_time": None,
            "start_address": pickup.get("address") or pickup.get("title") or "上車地點",
            "start_is_meeting_point": False,
            "start_latitude": pickup["latitude"],
            "start_longitude": pickup["longitude"],
            "stops": [{
                "address": destination.get("address") or destination.get("title") or "目的地",
                "latitude": destination["latitude"],
                "longitude": destination["longitude"],
            }],
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    quotes = []
    seen = set()
    for vehicle in payload.get("allVehicle") or []:
        if vehicle.get("fareGroup") != "fix_fare":
            continue

        vehicle_type = vehicle.get("vehicleType")
        label = TAXIGO_FIXED_FARE_LABELS.get(vehicle_type)
        if not label or label in seen:
            continue

        estimates = vehicle.get("fare", {}).get("estimate") or []
        if len(estimates) != 1:
            continue

        seen.add(label)
        eta = vehicle.get("estimateETA")
        quotes.append({
            "name": label,
            "fare": f"${int(estimates[0]):,}",
            "eta": _format_eta_seconds(eta),
        })

    return quotes


def fetch_taiwantaxi_quotes(pickup, destination):
    if not TAIWANTAXI_PREPARE_URL or not TAIWANTAXI_ESTIMATE_URL:
        raise RuntimeError("缺少 TAIWANTAXI_PREPARE_URL 或 TAIWANTAXI_ESTIMATE_URL")

    from_route = _taiwantaxi_route(pickup, default_provider=6, default_flag=3)
    to_route = _taiwantaxi_route(destination, default_provider=4, default_flag=1)
    print(f"55688 pickup location: {pickup}")
    print(f"55688 destination location: {destination}")
    print(f"55688 from route: {from_route}")
    print(f"55688 to route: {to_route}")
    prepare_payload = {
        "From": from_route,
        "To": to_route,
        "UserId": TAIWANTAXI_USER_ID,
    }
    if TAIWANTAXI_ACCESS_TOKEN:
        prepare_payload["AccessToken"] = TAIWANTAXI_ACCESS_TOKEN
    if TAIWANTAXI_SIGNATURE:
        prepare_payload["Signature"] = TAIWANTAXI_SIGNATURE

    prepare_response = requests.post(
        TAIWANTAXI_PREPARE_URL,
        headers=_taiwantaxi_headers(),
        json=prepare_payload,
        timeout=20,
    )
    prepare_response.raise_for_status()
    prepare_data = prepare_response.json()
    prepare_result = prepare_data.get("Result") or {}
    if prepare_result.get("State") not in (None, 0):
        print(f"55688 prepare warning: state={prepare_result.get('State')} msg={prepare_result.get('Msg')}")

    estimate_payload = {
        "Address": prepare_data.get("Address") or [
            {"Route": from_route, "Type": 1},
            {"Route": to_route, "Type": 2},
        ],
        "UserId": prepare_data.get("UserId") or TAIWANTAXI_USER_ID,
        "Time": prepare_data.get("Time") or TAIWANTAXI_TIME,
        "Signature": prepare_data.get("Signature") or TAIWANTAXI_SIGNATURE,
        "AccessToken": prepare_data.get("AccessToken") or TAIWANTAXI_ACCESS_TOKEN,
    }
    missing_fields = [key for key in ("UserId", "Time", "Signature", "AccessToken") if not estimate_payload.get(key)]
    if missing_fields:
        raise RuntimeError(f"55688 缺少必要欄位: {', '.join(missing_fields)}")

    estimate_response = requests.post(
        TAIWANTAXI_ESTIMATE_URL,
        headers=_taiwantaxi_headers(),
        json=estimate_payload,
        timeout=20,
    )
    estimate_response.raise_for_status()
    payload = estimate_response.json()
    print(f"55688 servicecards result: {(payload.get('Result') or {})}")

    quotes = _parse_taiwantaxi_quotes(payload)
    print(f"55688 parsed quotes: {quotes}")
    return quotes


def fetch_bolt_quotes(pickup, destination):
    required_fields = {
        "BOLT_AUTHORIZATION": BOLT_AUTHORIZATION,
        "BOLT_PAYMENT_METHOD_ID": BOLT_PAYMENT_METHOD_ID,
        "BOLT_DEVICE_ID": BOLT_DEVICE_ID,
        "BOLT_DISTINCT_ID": BOLT_DISTINCT_ID,
        "BOLT_RH_SESSION_ID": BOLT_RH_SESSION_ID,
        "BOLT_SESSION_ID": BOLT_SESSION_ID,
        "BOLT_USER_ID": BOLT_USER_ID,
    }
    missing = [key for key, value in required_fields.items() if not value]
    if missing:
        raise RuntimeError(f"缺少 {', '.join(missing)}")

    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate",
        "accept-language": "zh-TW,zh-Hant;q=0.9",
        "authorization": f"Bearer {BOLT_AUTHORIZATION}",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "user-agent": "Bolt/207748206 CFNetwork/3886.100.1 Darwin/27.0.0",
    }
    if BOLT_COOKIE:
        headers["cookie"] = BOLT_COOKIE

    params = {
        "brand": BOLT_BRAND,
        "country": BOLT_COUNTRY,
        "deviceId": BOLT_DEVICE_ID,
        "deviceType": BOLT_DEVICE_TYPE,
        "device_name": BOLT_DEVICE_NAME,
        "device_os_version": BOLT_DEVICE_OS_VERSION,
        "distinct_id": BOLT_DISTINCT_ID,
        "gps_accuracy_m": "10",
        "gps_age": "1",
        "gps_lat": pickup["latitude"],
        "gps_lng": pickup["longitude"],
        "language": BOLT_LANGUAGE,
        "lat": pickup["latitude"],
        "lng": pickup["longitude"],
        "rh_session_id": BOLT_RH_SESSION_ID,
        "session_id": BOLT_SESSION_ID,
        "user_id": BOLT_USER_ID,
        "version": BOLT_VERSION,
    }

    pickup_stop = {
        "lng": pickup["longitude"],
        "lat": pickup["latitude"],
        "is_confirmed": False,
    }
    place_id = pickup.get("provider_key") or pickup.get("place_id")
    if place_id:
        if not str(place_id).startswith("google|"):
            place_id = f"google|{place_id}"
        pickup_stop["place_id"] = place_id

    payload = {
        "addon_ids": [],
        "campaign_code": {},
        "timezone": "Asia/Taipei",
        "is_order_for_someone_else": False,
        "destination_stops": [{
            "lng": destination["longitude"],
            "lat": destination["latitude"],
        }],
        "payment_method": {
            "id": BOLT_PAYMENT_METHOD_ID,
            "type": BOLT_PAYMENT_METHOD_TYPE or "card",
        },
        "pickup_stop": pickup_stop,
    }

    response = requests.post(
        "https://user.live.boltsvc.net/rides/search/getRideOptions",
        headers=headers,
        params=params,
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("message") not in (None, "OK"):
        raise RuntimeError(payload.get("message") or "Bolt API error")

    categories = (((payload.get("data") or {}).get("ride_options") or {}).get("taxi") or {}).get("categories") or {}
    quotes = []
    seen = set()
    for item in categories.values():
        if not item.get("is_available"):
            continue
        label = _strip_html_text(item.get("name") or item.get("title_html") or "")
        fare = _bolt_original_fare(item.get("price") or {})
        if not label or not fare or (label, fare) in seen:
            continue
        seen.add((label, fare))
        quotes.append({
            "name": label,
            "fare": fare,
            "eta": _format_eta(_digits_only((item.get("eta_info") or {}).get("pickup_eta_str"))),
        })

    quotes.sort(key=lambda quote: _price_number(quote["fare"]))
    print(f"Bolt parsed quotes: {quotes}")
    return quotes


def _uber_cookie():
    if UBER_COOKIE:
        return UBER_COOKIE
    parts = []
    if UBER_COOKIE_SID:
        parts.append(f"sid={UBER_COOKIE_SID}")
    if UBER_COOKIE_CSID:
        parts.append(f"csid={UBER_COOKIE_CSID}")
    return "; ".join(parts)


def _taxigo_cookie():
    if TAXIGO_COOKIE:
        return TAXIGO_COOKIE
    parts = []
    if TAXIGO_TOKEN:
        parts.append(f"token={TAXIGO_TOKEN}")
    if TAXIGO_BILLING_TOKEN:
        parts.append(f"billing_token={TAXIGO_BILLING_TOKEN}")
    return "; ".join(parts)


def _taiwantaxi_headers():
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "connection": "keep-alive",
        "appversion": "10.5.1",
        "accept-language": "zh-tw",
        "accept-encoding": "br;q=1.0, gzip;q=0.9, deflate;q=0.8",
        "user-agent": "TaiwanTaxiClient/10.5.1 (tw.com.taiwantaxi.CallStation; build:2026060918302; iOS 27.0.0) Alamofire/5.10.2",
    }


def _taiwantaxi_route(location, default_provider, default_flag):
    known = (
        _match_known_taiwantaxi_route(location)
        or _google_place_detail_taiwantaxi_route(location)
        or _reverse_geocode_taiwantaxi_route(location)
    )
    address = location.get("address") or location.get("title") or ""
    title = location.get("title") or ""
    memo = location.get("memo") or title or _short_address_memo(address)
    route = {
        "AddrId": location.get("addr_id") or "",
        "ProviderKey": location.get("provider_key") or "",
        "DisplayTitle": title,
        "Lat": location["latitude"],
        "Lng": location["longitude"],
        "MemoForDriver": location.get("memo_for_driver") or "",
        "Memo": memo,
        "Address": address,
        "Accuracy": location.get("accuracy", 0),
        "Distance": location.get("distance", 0),
        "Flag": location.get("flag", default_flag),
        "City": location.get("city") or _extract_city(address),
        "Provider": location.get("provider", default_provider),
    }
    if known:
        route.update(known)
        route["Lat"] = location["latitude"]
        route["Lng"] = location["longitude"]
        if title:
            route["DisplayTitle"] = title
    return route


def _match_known_taiwantaxi_route(location):
    lat = round(float(location["latitude"]), 6)
    lng = round(float(location["longitude"]), 6)
    exact = TAIWANTAXI_KNOWN_ROUTES.get((lat, lng))
    if exact:
        return exact

    title = _normalize_text(location.get("title") or "")
    address = _normalize_text(location.get("address") or "")
    for (known_lat, known_lng), route in TAIWANTAXI_KNOWN_ROUTES.items():
        known_title = _normalize_text(route.get("Memo") or route.get("DisplayTitle") or "")
        known_address = _normalize_text(route.get("Address") or "")
        if title and known_title and (title in known_title or known_title in title):
            return route
        if address and known_address and (address in known_address or known_address in address):
            return route
        if abs(lat - known_lat) <= 0.001 and abs(lng - known_lng) <= 0.001:
            return route
    return None


def _reverse_geocode_taiwantaxi_route(location):
    if not TAIWANTAXI_GIS_REVERSE_URL or not TAIWANTAXI_ACCESS_TOKEN or not TAIWANTAXI_GIS_SIGNATURE:
        return None

    payload = {
        "UserId": TAIWANTAXI_USER_ID,
        "Mode": 1,
        "Caller": "APP55688-iOS",
        "ScenarioType": 1,
        "Lat": location["latitude"],
        "Lng": location["longitude"],
        "IsCompFavorite": 1,
        "AccessToken": TAIWANTAXI_ACCESS_TOKEN,
        "Signature": TAIWANTAXI_GIS_SIGNATURE,
    }
    try:
        response = requests.post(
            TAIWANTAXI_GIS_REVERSE_URL,
            headers=_taiwantaxi_headers(),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("Result") or {}
        if result.get("State") != 0:
            print(f"55688 GIS reverse warning: state={result.get('State')} msg={result.get('Msg')}")
            return None
        routes = data.get("Data") or []
        return routes[0] if routes else None
    except Exception as exc:
        print(f"55688 GIS reverse warning: {exc}")
        return None


def _google_place_detail_taiwantaxi_route(location):
    provider_key = location.get("provider_key")
    if not provider_key or not TAIWANTAXI_GOOGLE_PLACE_DETAILS_URL or not TAIWANTAXI_GOOGLE_PLACE_SIGNATURE:
        return None

    payload = {
        "UserId": TAIWANTAXI_USER_ID,
        "ProviderKey": provider_key,
        "Memo": location.get("memo") or location.get("title") or _short_address_memo(location.get("address") or ""),
        "Lng": 0,
        "Lat": 0,
        "AccessToken": TAIWANTAXI_ACCESS_TOKEN,
        "Signature": TAIWANTAXI_GOOGLE_PLACE_SIGNATURE,
    }
    try:
        response = requests.post(
            TAIWANTAXI_GOOGLE_PLACE_DETAILS_URL,
            headers=_taiwantaxi_headers(),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("Result") or {}
        if result.get("State") != 0:
            print(f"55688 GooglePlaceDetails warning: state={result.get('State')} msg={result.get('Msg')}")
            return None
        route = data.get("Data")
        if isinstance(route, dict):
            geocoder = route.get("Geocoder")
            if isinstance(geocoder, dict):
                return geocoder
            return route
        return None
    except Exception as exc:
        print(f"55688 GooglePlaceDetails warning: {exc}")
        return None


def _extract_city(address):
    if address.startswith("台北市") or address.startswith("臺北市"):
        return "台北市"
    if address.startswith("新北市"):
        return "新北市"
    if address.startswith("桃園市"):
        return "桃園市"
    return ""


def _short_address_memo(address):
    if not address:
        return ""
    parts = re.split(r"[市區路街段巷弄號]", address)
    for part in parts:
        part = part.strip()
        if part:
            return part[:20]
    return address[:20]


def _normalize_text(value):
    return re.sub(r"[\s台臺灣省市區路街段巷弄號樓之No.]", "", value or "").lower()


def _parse_taiwantaxi_quotes(payload):
    quotes = []
    seen = set()

    for group in payload.get("Data", {}).get("ServiceCardList") or []:
        for item in group.get("ServiceCardItems") or []:
            if not item.get("IsEnabled"):
                continue
            if not item.get("IsFixedPrice"):
                continue
            if item.get("DiscountedFinalFare") is not None:
                continue
            if item.get("FinalFare") in (None, ""):
                continue

            spec = item.get("SpecOrder") or {}
            if spec.get("AirportDropOff") or spec.get("Coupon"):
                continue

            label = _taiwantaxi_label(group, item)
            key = (label, item.get("FinalFare"))
            if not label or key in seen:
                continue

            seen.add(key)
            quotes.append({
                "name": label,
                "fare": f"${int(item['FinalFare']):,}",
                "eta": "",
            })

    quotes.sort(key=lambda quote: _price_number(quote["fare"]))
    return quotes


def _taiwantaxi_label(group, item):
    if item.get("AdTitle"):
        return item["AdTitle"]

    mode = item.get("Mode")
    spec = item.get("SpecOrder") or {}
    if spec.get("BabyTeam"):
        return "寶寶多元"

    if mode in TAIWANTAXI_MODE_LABELS:
        return TAIWANTAXI_MODE_LABELS[mode]

    category = group.get("CategoryName")
    if category == "car_card_category_suggested":
        return "多元"
    if category == "car_card_category_fixed_fare":
        return "55688 固定價"

    return None


def _is_single_twd_price(value):
    return bool(re.fullmatch(r"(NT)?\$[0-9,]+", value or ""))


def _strip_html_text(value):
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _digits_only(value):
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return int(digits) if digits else None


def _extract_price_from_html(value):
    match = re.search(r"\$([0-9,]+)", _strip_html_text(value))
    if not match:
        return ""
    return f"${match.group(1)}"


def _bolt_original_fare(price):
    original = _extract_price_from_html(price.get("second_line_html"))
    if original:
        return original

    current = _extract_price_from_html(price.get("first_line_html"))
    if current:
        return current

    actual = _digits_only(price.get("actual_str"))
    if actual is None:
        return ""
    return f"${actual:,}"


def _format_eta(minutes):
    if minutes is None:
        return ""
    try:
        return f"{int(minutes)} 分"
    except (TypeError, ValueError):
        return ""


def _format_eta_seconds(seconds):
    if not seconds:
        return ""
    try:
        minutes = max(1, round(int(seconds) / 60))
        return f"{minutes} 分"
    except (TypeError, ValueError):
        return ""


def _price_number(value):
    numbers = re.sub(r"[^0-9]", "", value or "")
    return int(numbers) if numbers else 0
