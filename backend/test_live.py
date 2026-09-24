import asyncio

from app.orchestrator import orchestrator


async def main():
    await orchestrator.bootstrap()
    state = orchestrator._current
    brief = state.get("brief") or {}
    sources = state.get("sources", {}).get("summary", {})
    wl = state.get("water_levels", [])
    precip = state.get("precipitation", [])
    wind = state.get("wind_grid", [])
    alerts = state.get("alerts", [])
    print("REGIONAL   :", state["regional"]["score"], state["regional"]["status"])
    print("BRIEF      :", brief.get("headline"))
    print("TRAFFIC    :", brief.get("traffic_light"), "|", brief.get("people_at_risk_text"))
    print("TOP AREAS  :", [a["name"] for a in brief.get("top_areas", [])[:5]])
    print("SOURCE LIVE:", sources.get("live"), "of", sources.get("total"))
    print("LIVE NAMES :", sources.get("live_names"))
    print("WATER LVLS :", len(wl), "| top:", wl[0]["station"], wl[0]["status"], "flow", wl[0].get("flow_ratio"))
    print("PRECIP     :", len(precip), "| top:", precip[0]["name"], precip[0]["rain_now_mm"], "mm", precip[0]["category"])
    print("WIND       :", len(wind), "| sample:", wind[0] if wind else None)
    print("ALERTS     :", len(alerts))
    print("ZONES>=40  :", len([z for z in state["zones"].values() if z["overall_score"] >= 40]))
    print("SOURCES    :")
    for s in state["sources"]["sources"]:
        print("   {:<20} {:<12} recs={}".format(s["key"], s["status"], s["records"]))


asyncio.run(main())