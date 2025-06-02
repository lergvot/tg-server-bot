# system_report.py
import asyncio
import datetime
import platform
import subprocess

import psutil


def format_uptime(td):
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def bytes_to_human_readable(num_bytes):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PiB"


def check_service(service_name):
    try:
        # Явно указываем путь к systemctl
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        status = result.stdout.strip()
        if not status:
            status = result.stderr.strip()
        return f"{service_name}: {status}"
    except Exception as e:
        return f"{service_name}: Error ({e})"


async def main(tgkey=None, chatID=None):
    try:
        uname = platform.uname()
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time

        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        swap = psutil.swap_memory()

        # Network usage
        net1 = psutil.net_io_counters()
        await asyncio.sleep(1)
        net2 = psutil.net_io_counters()
        bytes_sent = net2.bytes_sent - net1.bytes_sent
        bytes_recv = net2.bytes_recv - net1.bytes_recv
        net_usage = f"⬆️ {bytes_to_human_readable(bytes_sent)}/s | ⬇️ {bytes_to_human_readable(bytes_recv)}/s"

        # Алерты
        alerts = []
        if cpu_percent > 85:
            alerts.append("⚠️ High CPU usage!")
        if mem.percent > 90:
            alerts.append("⚠️ Memory usage critical!")
        if disk.percent > 90:
            alerts.append("⚠️ Disk space running low!")

        alert_text = "\n".join(alerts) if alerts else "✅ System health is OK"

        # --- Фикс топа процессов по CPU ---
        # Первый проход для инициализации cpu_percent
        for p in psutil.process_iter():
            try:
                p.cpu_percent(interval=None)
            except Exception:
                pass
        await asyncio.sleep(1)
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p)
            except Exception:
                pass
        top_procs = sorted(
            procs,
            key=lambda p: p.info["cpu_percent"],
            reverse=True,
        )[:3]

        proc_info = "\n".join(
            f"— *{p.info['name'] or 'Unknown'}* (PID `{p.info['pid']}`): `{p.info['cpu_percent']}%` CPU, `{p.info['memory_percent']:.1f}%` RAM"
            for p in top_procs
        )

        # Статус сервисов
        services_to_check = ["ssh", "nginx", "docker"]
        services_status = "\n".join(check_service(s) for s in services_to_check)

        # Финальное сообщение
        message = (
            "🖥️ *Server Report*\n"
            "========================\n"
            f"• Hostname: `{uname.node}`\n"
            f"• OS: `{uname.system} {uname.release}`\n"
            f"• Boot Time: `{boot_time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"• Uptime: `{format_uptime(uptime)}`\n"
            "------------------------\n"
            f"*CPU*: `{cpu_percent}%`\n"
            f"*RAM*: `{mem.percent}%` used ({bytes_to_human_readable(mem.used)})\n"
            f"*Swap*: `{swap.percent}%` used ({bytes_to_human_readable(swap.used)})\n"
            f"*Disk*: `{disk.percent}%` used ({bytes_to_human_readable(disk.used)})\n"
            f"*Network*: {net_usage}\n"
            "------------------------\n"
            f"*Status:*\n{alert_text}\n"
            "------------------------\n"
            "*Top Processes:*\n"
            f"{proc_info}\n"
            "------------------------\n"
            "*Services:*\n"
            f"{services_status}\n"
            "========================"
        )
        return message
    except Exception as e:
        print(f"[ERROR] {e}")
        return "Ошибка при формировании отчёта."


if __name__ == "__main__":
    asyncio.run(main())
