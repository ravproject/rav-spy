"""
Personalized Usage Optimization Advisor.
"""
from agent.analytics import usage_analytics


class Optimizer:
    async def generate_advice(self) -> str:
        peak = usage_analytics.get_peak_hours()
        top_features = usage_analytics.get_most_used_features(5)
        total = usage_analytics.get_total_commands()

        lines = ["📊 *Usage Optimization Advice*"]

        if total == 0:
            lines.append("\nBelum ada data penggunaan. Mulai gunakan fitur RAV-SPY!")
            return "\n".join(lines)

        if peak:
            hours_str = ", ".join(f"{h}:00" for h in peak)
            lines.append(f"\n⏰ Kamu paling aktif jam {hours_str}")
            lines.append(f"💡 Saran: Set `!focus` otomatis jam {peak[0]}:00 dengan `!schedule`")

        if top_features:
            lines.append(f"\n🔥 Fitur favorit ({total} total command):")
            for cmd, count in top_features:
                pct = count / total * 100
                lines.append(f"  • `!{cmd}` — {count}x ({pct:.0f}%)")

        lines.append(f"\n📈 Tips:")
        lines.append(f"  • Gunakan `!workspace save` untuk menyimpan sesi kerja")
        lines.append(f"  • Coba `!daily` untuk lihat aktivitas harian")
        lines.append(f"  • Aktifkan `!focus` untuk mode Pomodoro")
        lines.append(f"  • Pakai `!memory` untuk ingatan jangka panjang")

        return "\n".join(lines)


optimizer = Optimizer()
