#!/bin/bash
# One-time diagnostic: live_report with 10h window
# Usage: bash infra/report_10h.sh
exec > /tmp/live_report.txt 2>&1
WINDOW="10 hours ago"
echo "=== POKEMON MONITOR — 10H REPORT ($(date '+%Y-%m-%d %H:%M')) ==="
echo ""
LOGS=$(journalctl -u pokemon-monitor-v2 --since "$WINDOW" --no-pager -o cat 2>/dev/null)
if [ -z "$LOGS" ]; then echo "(no logs)"; exit 0; fi

echo "=== SHOPY — SKANY (last 10h, grouped) ==="
echo ""
echo "$LOGS" | awk '
function get_shop(line,    n, parts, i, name) {
    n = split(line, parts, "[")
    name = ""
    for (i = 1; i <= n; i++) {
        sub(/\].*/, "", parts[i])
        if (parts[i] ~ /^ENGINE:/) { sub(/^ENGINE:/, "", parts[i]); name = parts[i]; break }
        if (parts[i] !~ /^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR|CF_SOLVER|MAIN)$/ && parts[i] ~ /^[a-zA-Z]/ && parts[i] ~ /[a-z]/) name = parts[i]
    }
    return name
}
function get_group(line,    n, parts, i) {
    n = split(line, parts, "[")
    for (i = 1; i <= n; i++) {
        sub(/\].*/, "", parts[i])
        if (parts[i] ~ /^ENGINE:/) return "ENGINE"
        if (parts[i] == "FAST" || parts[i] == "SLOW" || parts[i] == "NODRIVER" || parts[i] == "ENGINE") return parts[i]
    }
    return "?"
}
/produkt.*w [0-9.]+s/ {
    shop = get_shop($0); if (shop == "") next
    grp = get_group($0); shop_group[shop] = grp
    nw = split($0, words, " ")
    for (wi = 1; wi <= nw; wi++) if (words[wi] ~ /^produkt/) { last_products[shop] = words[wi-1]+0; break }
    t = -1
    for (wi = 1; wi <= nw; wi++) if (words[wi] == "w" && wi < nw) { tstr = words[wi+1]; gsub(/s$/, "", tstr); if (tstr ~ /^[0-9.]+$/) t = tstr+0.0; break }
    scan_count[shop]++
    if (t >= 0) scan_time_sum[shop] += t
}
/[Tt]imeout/ { shop = get_shop($0); if (shop != "") timeout_count[shop]++; grp = get_group($0); if (shop != "" && grp != "?") shop_group[shop] = grp }
/\[ERROR\]/ { shop = get_shop($0); if (shop != "") error_count[shop]++; grp = get_group($0); if (shop != "" && grp != "?") shop_group[shop] = grp }
END {
    for (s in scan_count) all_shops[s] = 1
    for (s in timeout_count) all_shops[s] = 1
    for (s in error_count) all_shops[s] = 1
    n = 0
    for (s in all_shops) { n++; names[n] = s; counts[n] = scan_count[s]+0 }
    for (i = 1; i <= n; i++) for (j = i+1; j <= n; j++) if (counts[j] > counts[i]) { tmp=counts[i]; counts[i]=counts[j]; counts[j]=tmp; tmp=names[i]; names[i]=names[j]; names[j]=tmp }
    for (i = 1; i <= n; i++) { s = names[i]; g = shop_group[s]; if (g == "") g = "?"; group_shops[g] = group_shops[g] " " i }
    split("FAST SLOW NODRIVER ENGINE ?", grp_order, " ")
    total_scans=0; total_tout=0; total_err=0; shops_ok=0; shops_sick=0; shops_dead=0
    for (gi = 1; gi <= 5; gi++) {
        g = grp_order[gi]; if (!(g in group_shops)) continue
        split(group_shops[g], idxs, " "); grp_count=0; grp_scans=0
        for (k in idxs) { if (idxs[k]=="") continue; grp_count++; grp_scans += scan_count[names[idxs[k]+0]]+0 }
        printf "\n  --- %s (%d shops, %d scans/10h) ---\n", g, grp_count, grp_scans
        printf "  %-22s %6s %6s %5s %4s %4s  %s\n", "SHOP", "SCANS", "AVG", "PRODS", "TOUT", "ERR", "STATUS"
        for (k = 1; k <= length(idxs); k++) {
            if (idxs[k]=="") continue; idx=idxs[k]+0; s=names[idx]
            sc=scan_count[s]+0; tc=timeout_count[s]+0; ec=error_count[s]+0; prods=last_products[s]+0
            total_scans+=sc; total_tout+=tc; total_err+=ec
            avg_str = (sc>0) ? sprintf("%.0fs", scan_time_sum[s]/sc) : "-"
            if (sc==0) { status="DEAD"; shops_dead++ }
            else if (tc>0 && (tc*100/(sc+tc))>30) { status="SICK"; shops_sick++ }
            else if (ec>0 && (ec*100/sc)>20) { status="SICK"; shops_sick++ }
            else { status="OK"; shops_ok++ }
            printf "  %-22s %6d %6s %5d %4d %4d  %s\n", s, sc, avg_str, prods, tc, ec, status
        }
    }
    printf "\n  ================================================\n"
    printf "  SCANNING: %d | SICK: %d | DEAD: %d\n", shops_ok, shops_sick, shops_dead
    printf "  Total: %d scans/10h | %d timeouts | %d errors\n", total_scans, total_tout, total_err
}
'
echo ""
echo "=== HEALS (10h) ==="
echo "$LOGS" | grep -i "heal #\|heal limit\|cooldown 30min" | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG|BROWSER_MGR)$' | sort | uniq -c | sort -rn | head -15 | awk '{printf "  %3d x %s\n", $1, $2}'
TOTAL_HEALS=$(echo "$LOGS" | grep -ci "heal #\|Healing page")
echo "  Total heals: $TOTAL_HEALS"
echo ""
echo "=== TIMEOUTY (10h) ==="
echo "$LOGS" | grep -i 'timeout' | grep -oP '\[\K[a-zA-Z][\w-]*(?=\])' | grep -vE '^(FAST|SLOW|NODRIVER|ENGINE|INFO|WARNING|ERROR|DEBUG)$' | sort | uniq -c | sort -rn | head -20 | awk '{printf "  %3d x %s\n", $1, $2}'
TOTAL_TOUT=$(echo "$LOGS" | grep -ci 'timeout')
echo "  Total timeouts: $TOTAL_TOUT"
echo ""
echo "=== DONE ==="
echo "Report saved to /tmp/live_report.txt" >&2
