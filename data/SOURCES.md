# Data sources and method

All prices are retail pump prices **including taxes**, in **US dollars per litre**, monthly, January 1999 to October 2026.
Gasoline = Euro-super 95 / unleaded 95 (Russia AI-95, China 92#). Diesel = automotive gas oil.

| Country / period | Source | Raw file |
|---|---|---|
| EU-27, 2005 (BG/RO 2008, HR 2013) to 19 Oct 2026; UK 2005-2020 | European Commission, Weekly Oil Bulletin, *Prices history* (prices with taxes, EUR per 1000 l). Monthly average of weekly values. | `raw/eu_wob_monthly_eur_per_1000l.txt` |
| UK 2021 to 26 Oct 2026 | UK Department for Energy Security and Net Zero, *Weekly road fuel prices* (accredited official statistics), pence per litre | `raw/uk_desnz_weekly_road_fuel_monthly_pence_per_l.txt` |
| Norway 1999 to Sep 2026 | Statistics Norway (SSB), table 09654, NOK per litre | `raw/norway_ssb_09654_nok_per_l.txt` |
| Switzerland, Iceland, Türkiye, Serbia, Dec 2016 onward | Level from World Bank/GIZ (Nov 2016), moved forward with Eurostat HICP sub-indices CP07222 Petrol and CP07221 Diesel (`prc_hicp_minr`) | `raw/eurostat_hicp_fuels_and_fx.txt` |
| Switzerland 2025 to Oct 2026 | Federal Office for Customs and Border Security (BAZG), table T 4.5, pump prices in the border zone (Basel), Rappen per litre | `raw/other_sources_ch_cn_rub.txt` |
| Russia | Rosstat: average consumer prices, end of year 1999-2025 (AI-95; AI-92 for 1999-2000 scaled), weekly AI-95 and diesel 2022 to 19 Oct 2026. Diesel before 2022 = gasoline x diesel/gasoline ratio (World Bank 1998-2016, Rosstat 2022+, interpolated) | `raw/russia_rosstat_fuel_prices_rub_per_l.txt` |
| China | World Bank/GIZ to 2016; 92# annual levels 2017-2023 (press compilation of NDRC-capped prices); Apr 2024 to Sep 2026 NDRC retail cap adjustments chained from the Shanghai DRC notice of 9 Mar 2026 (92#: 7.60 CNY/l, 0# diesel: 7.28 CNY/l) | `raw/other_sources_ch_cn_rub.txt` |
| All countries 1999-2004 (and the gaps above) | World Bank WDI Database Archives (EP.PMP.SGAS.CD, EP.PMP.DESL.CD), based on the GIZ *International Fuel Prices* survey, mid-November every two years | `raw/worldbank_wdi_archive_pump_prices_usd_per_l.txt` |

## Exchange rates
* Eurostat `ert_bil_eur_m`, monthly averages (USD, GBP, NOK, CHF, ISK, TRY, RSD, CNY, RUB to Feb 2022). Oct 2026 uses the Sep 2026 rate.
* RUB after Feb 2022: OECD MEI via FRED (CCUSSP02RUM650N) to Nov 2023, Bank of Russia official monthly averages 2024-2026.

## Interpolation (be transparent about it)
* Monthly data is used as is. Sparse points (World Bank snapshots, annual values) are joined with monotone cubic (PCHIP) interpolation.
* From 2005, gaps between World Bank snapshots for CH, IS, TR, RS, HR, BG, RO are shaped by the EU-average monthly path (country/EU ratio interpolated, official snapshot values kept exactly).
* The animation applies a light 3-month centred average so weekly noise does not make bars jitter.

## Known limitations
* Values for China 2017-2023 and Russian diesel 2017-2021 are the weakest part of the dataset (annual or ratio-based).
* Swiss 2025-2026 prices are border-zone (Basel) prices, close to but not identical with the national average.
* Converting to USD means currency moves (for example the Turkish lira) change the ranking as much as pump prices do.
