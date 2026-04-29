# V6 Matching Report

Generated: 2026-02-25 03:08:02 UTC

## Summary

- Input file: `OIM/FirstPass/texas_matched_substations_v5.csv`
- Output file: `OIM/FirstPass/texas_matched_substations_v6.csv`
- Strict auto-accepted snaps (<= 1.0 km): **158**
- Review queue (>1.0 and <= 2.0 km): **28**

## Match Source Delta

| Source | V5 | V6 | Delta |
|---|---|---|---|
| cp_osm | 35 | 35 | +0 |
| eia860 | 241 | 165 | -76 |
| gnis | 929 | 929 | +0 |
| hv_endpoint | 223 | 223 | +0 |
| hv_osm_345 | 27 | 27 | +0 |
| lz_centroid | 477 | 477 | +0 |
| mora_county_centroid | 5 | 5 | +0 |
| mora_eia860 | 178 | 96 | -82 |
| mora_ix_queue | 8 | 8 | +0 |
| mora_osm | 35 | 35 | +0 |
| osm | 1039 | 1039 | +0 |
| propagated | 1757 | 1757 | +0 |
| snap_eia860 | 0 | 76 | +76 |
| snap_mora_eia860 | 0 | 82 | +82 |

## Confidence Delta

| Confidence | V5 | V6 | Delta |
|---|---|---|---|
| high | 1590 | 1480 | -110 |
| medium | 902 | 1012 | +110 |
| low | 1985 | 1985 | +0 |
| none | 477 | 477 | +0 |

## New Auto-Attached OSM Bindings

| Substation | Original Source | Original Conf | New Source | OSM ID | OSM Name | Distance (km) |
|---|---|---|---|---|---|---|
| MESTENO | eia860 | high | snap_eia860 | 1010864084 |  | 0.005 |
| AUSTIN | eia860 | high | snap_eia860 | 223939599 | Austin Dam Substation | 0.007 |
| PUEBLO | eia860 | high | snap_eia860 | 427460106 | Pueblo Substation | 0.007 |
| DICKNSON | eia860 | high | snap_eia860 | 336628606 | Dickinson Substation | 0.009 |
| ANGLETON | eia860 | high | snap_eia860 | 338876675 | Angleton Substation | 0.012 |
| LOPENO | eia860 | high | snap_eia860 | 453123230 | Lopeno Substation | 0.013 |
| BATCAVE | eia860 | high | snap_eia860 | 192674614 | Fort Mason Substation | 0.013 |
| SWEENY | eia860 | high | snap_eia860 | 338876677 | Sweeny Substation | 0.015 |
| ZAPATA | eia860 | high | snap_eia860 | 21399591 | Zapata Substation | 0.018 |
| HWF | mora_eia860 | high | snap_mora_eia860 | 171742083 | Hackberry Wind Substation | 0.023 |
| CITRUSCY | eia860 | medium | snap_eia860 | 512042596 | Citrus City Substation | 0.024 |
| CORPUS | eia860 | medium | snap_eia860 | 488508185 |  | 0.024 |
| CANYON | eia860 | high | snap_eia860 | 341093644 |  | 0.025 |
| COTPLNS | mora_eia860 | high | snap_mora_eia860 | 505843813 |  | 0.028 |
| EAGLE_PS | eia860 | medium | snap_eia860 | 21107682 | Eagle Hydro Substation | 0.028 |
| ALVIN | eia860 | high | snap_eia860 | 338305186 | Alvin Substation | 0.029 |
| MARBFA | mora_eia860 | high | snap_mora_eia860 | 504607219 | Marble Falls Substation | 0.030 |
| PROSPERO | eia860 | high | snap_eia860 | 1058281178 |  | 0.031 |
| STELLA | eia860 | high | snap_eia860 | 1060258402 |  | 0.031 |
| BRAZORIA | eia860 | high | snap_eia860 | 338876676 | Brazoria Substation | 0.032 |
| TXCTY | mora_eia860 | high | snap_mora_eia860 | 338819909 |  | 0.033 |
| HEIGHTTN | eia860 | medium | snap_eia860 | 338794655 | Heights Substation | 0.034 |
| WFTANK | mora_eia860 | high | snap_mora_eia860 | 1432429856 |  | 0.036 |
| SKY1 | mora_eia860 | high | snap_mora_eia860 | 520305127 | Rock Island Substation | 0.038 |
| MIRASOLE | mora_eia860 | high | snap_mora_eia860 | 512054197 | Los Mirasoles Substation | 0.040 |
| WIPOPA | mora_eia860 | high | snap_mora_eia860 | 510839019 | Winchester Power Park Substation | 0.041 |
| FREC | mora_eia860 | high | snap_mora_eia860 | 172583750 | Richland Chambers Substation | 0.042 |
| ZIER_SLR | eia860 | medium | snap_eia860 | 1009124703 | Pinto Creek Substation | 0.043 |
| FTWIND | mora_eia860 | high | snap_mora_eia860 | 632208845 | Tater Hill Substation | 0.045 |
| KEECHI | eia860 | high | snap_eia860 | 1122955349 |  | 0.055 |
| CHAMPION | eia860 | high | snap_eia860 | 171793190 | Champion Wind Farm Substation | 0.056 |
| GRAHAM | eia860 | high | snap_eia860 | 171410641 |  | 0.059 |
| PALMAS | eia860 | medium | snap_eia860 | 1060258409 |  | 0.062 |
| PEARSALL | eia860 | high | snap_eia860 | 125729481 | Pearsall Switchyard | 0.069 |
| WAP | mora_eia860 | high | snap_mora_eia860 | 39610469 | W. A. Parish Station (138 kV) | 0.074 |
| MIL | mora_eia860 | high | snap_mora_eia860 | 1104531038 |  | 0.074 |
| GRDNE | mora_eia860 | high | snap_mora_eia860 | 499731314 | Garden City East Substation | 0.077 |
| MYR | mora_eia860 | high | snap_mora_eia860 | 1266968859 |  | 0.080 |
| IMPACT | eia860 | high | snap_eia860 | 1058316820 |  | 0.080 |
| TKWSW1 | mora_eia860 | medium | snap_mora_eia860 | 171793197 | Roscoe Wind Farm Substation | 0.082 |
| MNWLE | mora_eia860 | high | snap_mora_eia860 | 767306753 |  | 0.083 |
| FRMRSVLW | mora_eia860 | medium | snap_mora_eia860 | 754620179 |  | 0.085 |
| WHMESA | mora_eia860 | high | snap_mora_eia860 | 1191329163 |  | 0.086 |
| LFSTH | mora_eia860 | high | snap_mora_eia860 | 362672245 | Lufkin South Substation | 0.087 |
| GRIFFITH | eia860 | medium | snap_eia860 | 125895679 | Robinson Northwest Substation | 0.087 |
| BIG_STAR | eia860 | medium | snap_eia860 | 1157940852 |  | 0.088 |
| NACPW | mora_eia860 | high | snap_mora_eia860 | 748882244 |  | 0.089 |
| OLINGR | mora_eia860 | high | snap_mora_eia860 | 283611943 |  | 0.091 |
| SJS | mora_eia860 | medium | snap_mora_eia860 | 51445934 |  | 0.096 |
| SPLAIN1 | mora_eia860 | medium | snap_mora_eia860 | 490163643 | South Plains Wind 2 Substation | 0.097 |
| GREGORY | eia860 | high | snap_eia860 | 514740646 | Gregory Switchyard | 0.098 |
| ROUTE_66 | eia860 | high | snap_eia860 | 453794544 | Route 66 Wind Substation | 0.100 |
| CISC | mora_eia860 | high | snap_mora_eia860 | 570716969 |  | 0.103 |
| SBEAN | mora_eia860 | medium | snap_mora_eia860 | 501477437 | Screwbean Substation | 0.103 |
| ECEC | mora_eia860 | high | snap_mora_eia860 | 457948523 | Ector County Energy Center Substation | 0.104 |
| SANDLAKE | eia860 | high | snap_eia860 | 1006401457 | Mcllvain Substation | 0.107 |
| PAVO_ESS | eia860 | medium | snap_eia860 | 503096006 | White Baker Substation | 0.112 |
| WHCCS | mora_eia860 | medium | snap_mora_eia860 | 862801075 | Wolf Hollow Substation | 0.116 |
| CATARINA | eia860 | medium | snap_eia860 | 822462023 |  | 0.120 |
| RAMBLER | eia860 | high | snap_eia860 | 1009208939 |  | 0.122 |
| ARAGORN | eia860 | medium | snap_eia860 | 1202669863 |  | 0.122 |
| JDKNS | mora_eia860 | high | snap_mora_eia860 | 459878020 | Judkins Substation | 0.125 |
| SILASRAY | mora_eia860 | high | snap_mora_eia860 | 513680410 | Power Plant Substation | 0.126 |
| PARIS | eia860 | high | snap_eia860 | 1095466306 |  | 0.126 |
| N_LAKE_D | eia860 | high | snap_eia860 | 341162172 | North Lake Substation | 0.126 |
| BAFFIN | eia860 | high | snap_eia860 | 511539430 | Baffin Substation | 0.130 |
| SPNCER | eia860 | high | snap_eia860 | 374065818 |  | 0.131 |
| SALVTION | mora_eia860 | high | snap_mora_eia860 | 1060364773 |  | 0.133 |
| SCSES | mora_eia860 | high | snap_mora_eia860 | 748882246 |  | 0.134 |
| FRONTERA | eia860 | high | snap_eia860 | 838284171 | Energía Buena Vista | 0.136 |
| CRANELL | eia860 | medium | snap_eia860 | 1095737661 |  | 0.140 |
| SHANNON | eia860 | high | snap_eia860 | 686972909 |  | 0.148 |
| BASTEN | mora_eia860 | medium | snap_mora_eia860 | 173298456 | Bastrop Energy Switchyard | 0.149 |
| CBEC | mora_eia860 | high | snap_mora_eia860 | 520385215 | Colorado Bend Substation | 0.150 |
| DDPEC | mora_eia860 | high | snap_mora_eia860 | 1350437811 |  | 0.152 |
| GUADG | mora_eia860 | high | snap_mora_eia860 | 174246135 | Guadalupe Generating Station | 0.152 |
| TGCCS | mora_eia860 | high | snap_mora_eia860 | 172364113 | Tenaska Gateway Station | 0.153 |
| DNDAM | eia860 | high | snap_eia860 | 633619447 | Denison Dam Substation | 0.156 |
| BEXAR_ES | eia860 | high | snap_eia860 | 1428418588 |  | 0.157 |
| LONESTAR | eia860 | high | snap_eia860 | 501745978 | Lonestar Substation | 0.158 |
| MCSES | mora_eia860 | high | snap_mora_eia860 | 29185987 |  | 0.167 |
| LAREDO | eia860 | high | snap_eia860 | 451971663 | Laredo Plant Substation | 0.171 |
| MGSES | mora_eia860 | high | snap_mora_eia860 | 171802233 | Morgan Creek Substation | 0.176 |
| STEAM | mora_eia860 | high | snap_mora_eia860 | 283611932 |  | 0.176 |
| DEC | mora_eia860 | medium | snap_mora_eia860 | 864993512 |  | 0.177 |
| OECCS | mora_eia860 | high | snap_mora_eia860 | 172212642 |  | 0.178 |
| FTDUNCAN | mora_eia860 | high | snap_mora_eia860 | 20841019 | Rosita Creek Substation | 0.180 |
| PSG | mora_eia860 | medium | snap_mora_eia860 | 337194142 | Davson Substation | 0.180 |
| CHISMGRD | mora_eia860 | medium | snap_mora_eia860 | 1319707419 |  | 0.181 |
| WILDCAT | eia860 | medium | snap_eia860 | 1105404316 |  | 0.185 |
| QALSW | mora_eia860 | high | snap_mora_eia860 | 172212625 | Quail Substation | 0.187 |
| DANSBY | eia860 | high | snap_eia860 | 100306757 | Dansby Substation | 0.187 |
| FAULKNER | eia860 | high | snap_eia860 | 501745940 | Faulkner Substation | 0.204 |
| TEN | mora_eia860 | high | snap_mora_eia860 | 172362138 |  | 0.206 |
| ESTONIAN | eia860 | medium | snap_eia860 | 1157165696 |  | 0.206 |
| GIDEON | mora_eia860 | high | snap_mora_eia860 | 127247651 | Sim Gideon Station | 0.210 |
| CBY | mora_eia860 | high | snap_mora_eia860 | 39962537 | Cedar Bayou Plant Substation | 0.213 |
| HOLCOMB | eia860 | high | snap_eia860 | 21073895 | Holcomb Substation | 0.224 |
| LARDVFTN | mora_eia860 | medium | snap_mora_eia860 | 426016265 | Laredo Plant Statcom Substation | 0.232 |
| PHOEBE | eia860 | high | snap_eia860 | 1009182707 |  | 0.237 |
| PISGAH | eia860 | medium | snap_eia860 | 1162794463 |  | 0.240 |
| LEON_CRK | eia860 | medium | snap_eia860 | 317830185 | Leon Creek Switchyard | 0.241 |
| WESTOVER | eia860 | high | snap_eia860 | 457746513 | Westover Substation | 0.243 |
| LHSES | mora_eia860 | high | snap_mora_eia860 | 30741837 | Lake Hubbard Station | 0.244 |
| DECKER | eia860 | medium | snap_eia860 | 276827871 | Decker Switchyard | 0.244 |
| THW | mora_eia860 | high | snap_mora_eia860 | 586730852 | T. H. Wharton Substation | 0.245 |
| HANDLEY | eia860 | high | snap_eia860 | 28267083 |  | 0.252 |
| DIBOL | mora_eia860 | high | snap_mora_eia860 | 507436950 | Diboll Substation | 0.253 |
| GANADO | eia860 | high | snap_eia860 | 1458653861 | Ganado Substation | 0.259 |
| LON | mora_eia860 | high | snap_mora_eia860 | 336253179 | Liverpool Substation | 0.281 |
| HELENA | eia860 | high | snap_eia860 | 1095745281 |  | 0.287 |
| GANADOS | eia860 | high | snap_eia860 | 1458653862 | Ricebird STEC Switchyard | 0.291 |
| PAULN | mora_eia860 | high | snap_mora_eia860 | 533856034 |  | 0.293 |
| SCES | mora_eia860 | high | snap_mora_eia860 | 125920534 | Rattlesnake Road Substation | 0.321 |
| FLOWERII | mora_eia860 | high | snap_mora_eia860 | 501745939 | Flat Top Substation | 0.322 |
| SANMIGL | mora_eia860 | high | snap_mora_eia860 | 174405327 | San Miguel Switchyard | 0.328 |
| NEDIN | mora_eia860 | high | snap_mora_eia860 | 174789429 | North Edinburg Substation | 0.332 |
| WHCCS2 | mora_eia860 | medium | snap_mora_eia860 | 171853245 | Wolf Hollow Substation | 0.334 |
| PB2SES | mora_eia860 | high | snap_mora_eia860 | 460049101 | Permian Basin Station | 0.345 |
| TNSKA | mora_eia860 | medium | snap_mora_eia860 | 478412024 |  | 0.378 |
| BLUEJAY | mora_eia860 | high | snap_mora_eia860 | 1163028696 |  | 0.392 |
| TAHOKA | eia860 | high | snap_eia860 | 1021855841 |  | 0.407 |
| PEARSAL1 | eia860 | medium | snap_eia860 | 344086388 |  | 0.413 |
| CPSES | mora_eia860 | high | snap_mora_eia860 | 39683503 | Comanche Peak Station | 0.419 |
| EXGNWTL | mora_eia860 | high | snap_mora_eia860 | 451971738 | Whitetail Substation | 0.420 |
| OGSES | mora_eia860 | medium | snap_mora_eia860 | 172715380 | Oak Grove Substation | 0.441 |
| LAPETUS | eia860 | high | snap_eia860 | 1058327753 |  | 0.448 |
| FRNYPP | mora_eia860 | medium | snap_mora_eia860 | 39952562 | Forney Substation | 0.451 |
| GBY | mora_eia860 | high | snap_mora_eia860 | 336813657 | Greens Bayou 345kV Substation | 0.454 |
| RRANCHES | mora_eia860 | high | snap_mora_eia860 | 1006929084 |  | 0.463 |
| COLETO | eia860 | medium | snap_eia860 | 174682092 | Coleto Creek Substation | 0.472 |
| COYOTSPR | mora_eia860 | medium | snap_mora_eia860 | 501745945 | Reeves County #4 Substation | 0.478 |
| SEADRIFT | eia860 | medium | snap_eia860 | 515325952 | Airco Substation | 0.478 |
| BAKKE | eia860 | high | snap_eia860 | 459062067 | Bakke Substation | 0.503 |
| TRUSGILL | mora_eia860 | high | snap_mora_eia860 | 1112112902 |  | 0.505 |
| HOLSTEIN | eia860 | high | snap_eia860 | 1058313857 |  | 0.510 |
| GRAHM | eia860 | high | snap_eia860 | 171410588 | Graham Substation | 0.511 |
| SADLBACK | eia860 | medium | snap_eia860 | 1007123849 | Eagle Claw Midstream Substation | 0.513 |
| LV5 | mora_eia860 | high | snap_mora_eia860 | 453015259 | LKHoward Substation | 0.544 |
| DIGBY | mora_eia860 | high | snap_mora_eia860 | 498907635 | Bendix Substation | 0.551 |
| LEG | mora_eia860 | high | snap_mora_eia860 | 100353514 | Limestone Station | 0.552 |
| BULLCRK | eia860 | medium | snap_eia860 | 467959357 | Bull Creek Wind Substation | 0.555 |
| X4 | mora_eia860 | medium | snap_mora_eia860 | 278460528 | Southwest Research Institute Substation | 0.558 |
| AE | mora_eia860 | medium | snap_mora_eia860 | 1340873336 |  | 0.564 |
| STP | mora_eia860 | medium | snap_mora_eia860 | 39832667 | South Texas Project Switchyard | 0.576 |
| LILY | eia860 | medium | snap_eia860 | 1087366829 |  | 0.578 |
| MLSES | mora_eia860 | high | snap_mora_eia860 | 172343969 | Martin Lake Substation | 0.581 |
| CONIGLIO | eia860 | high | snap_eia860 | 1070460974 |  | 0.640 |
| UPTON | eia860 | medium | snap_eia860 | 579799483 | Upton County Solar 2 Substation | 0.652 |
| MESQCRK | mora_eia860 | high | snap_mora_eia860 | 453377005 | Mesquite Creek Wind Substation | 0.708 |
| SWEETWN5 | mora_eia860 | high | snap_mora_eia860 | 171934656 | Sweetwater Wind 5 Substation | 0.713 |
| WEBBER | mora_eia860 | medium | snap_mora_eia860 | 462642773 | Webberville Solar Substation | 0.750 |
| WOVER | mora_eia860 | medium | snap_mora_eia860 | 457746512 | Amoco South Foster Substation | 0.755 |
| MISAE | eia860 | high | snap_eia860 | 1148040638 |  | 0.849 |
| LONEWOLF | mora_eia860 | medium | snap_mora_eia860 | 171934655 | Loraine Wind Farm Substation | 0.867 |
| BRIAR | eia860 | medium | snap_eia860 | 1087366819 |  | 0.884 |
| NUECES_B | eia860 | medium | snap_eia860 | 422732473 | Citgo North Oak Park Substation | 0.970 |
| WHITNEY | eia860 | high | snap_eia860 | 172714141 | Whitney Switching Station | 0.984 |

## Review Queue (1-2 km, not applied)

| Substation | Original Source | Original Conf | Nearest OSM ID | OSM Name | Distance (km) |
|---|---|---|---|---|---|
| LACY_CRK | eia860 | medium | 1191329509 |  | 1.040 |
| OWF | mora_eia860 | medium | 172212626 | Elbow Creek Wind Farm | 1.044 |
| OCOTILLO | eia860 | medium | 172212626 | Elbow Creek Wind Farm | 1.044 |
| ELB | mora_eia860 | medium | 468019561 | Ocotillo Wind Substation | 1.084 |
| WND | mora_eia860 | medium | 172714154 | Lake Whitney Substation | 1.086 |
| WHTNY | eia860 | medium | 172714154 | Lake Whitney Substation | 1.086 |
| ELLISSLR | mora_eia860 | medium | 1302777336 |  | 1.131 |
| CORAZON | eia860 | medium | 1350503758 |  | 1.213 |
| AJAXWIND | mora_eia860 | medium | 1136041937 | Western Trail Wind Farm Substation | 1.239 |
| ALAMO_ST | eia860 | medium | 496524847 | Pearl Substation | 1.249 |
| WHITSBOR | eia860 | medium | 442929247 |  | 1.252 |
| BTM | mora_eia860 | high | 339232125 | Rosharon Substation | 1.278 |
| FLTCK | mora_eia860 | medium | 527832010 | Silver Star Wind Substation | 1.288 |
| MDANP | mora_eia860 | high | 1466128997 |  | 1.314 |
| BRTSW | mora_eia860 | high | 171451771 |  | 1.347 |
| LV3 | mora_eia860 | medium | 512360983 | Rio Grande City Substation | 1.405 |
| PINEFRST | eia860 | medium | 631186752 | Champion Paper Mill Substation | 1.459 |
| CRANE | eia860 | medium | 499938053 | Spudder Flat Substation | 1.459 |
| REROCK | mora_eia860 | high | 500535874 | Clovis Substation | 1.599 |
| JOHNSON | eia860 | medium | 455340176 |  | 1.600 |
| GREASWOD | eia860 | medium | 1006095181 |  | 1.604 |
| TAYGETE | eia860 | medium | 1087292778 |  | 1.651 |
| TYLRWIND | mora_eia860 | medium | 1144482433 |  | 1.751 |
| DERMOTT | eia860 | high | 1452973269 |  | 1.806 |
| DMTSW | eia860 | medium | 1452973269 |  | 1.806 |
| CFLATS | mora_eia860 | medium | 1107612363 |  | 1.864 |
| TTWEC | mora_eia860 | high | 491192926 | Turkey Track Wind Substation | 1.920 |
| TURKEY | eia860 | medium | 491192926 | Turkey Track Wind Substation | 1.920 |

## Notes

- Auto-attach candidates were restricted to `eia860` and `mora_eia860` rows with `high/medium` confidence and empty `osm_id`.
- Nearest-node search was constrained to the same ERCOT load zone polygon.
- Auto-accepted rows were marked `match_source = snap_<original_source>` and conservatively downgraded to `confidence = medium`.
