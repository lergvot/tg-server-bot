# system_report.py
import asyncio
import datetime
import html
import logging
import platform
import subprocess

import psutil

logger = logging.getLogger("system_report")

SYSTEMCTL_PATH = "/usr/bin/systemctl"


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


def escape_html(text):
    """Экранирует HTML-сущности в тексте"""
    if text is None:
        return ""
    return html.escape(str(text))


def check_service(service_name):
    """Проверить статус системного сервиса"""
    try:
        result = subprocess.run(
            [SYSTEMCTL_PATH, "is-active", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        status = result.stdout.strip()
        if not status:
            status = result.stderr.strip()

        status_translations = {
            "active": "активен",
            "inactive": "неактивен",
            "failed": "ошибка",
            "activating": "запускается",
            "deactivating": "останавливается",
        }

        translated_status = status_translations.get(status, status)
        return f"{service_name}: {translated_status}"
    except subprocess.TimeoutExpired:
        return f"{service_name}: таймаут проверки"
    except Exception as e:
        logger.error(f"Ошибка при проверке сервиса {service_name}: {e}")
        return f"{service_name}: ошибка ({str(e)[:30]})"


async def get_docker_containers():
    """Получаем информацию о работающих Docker контейнерах"""
    try:
        result = subprocess.run(
            [
                "/usr/bin/docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.Container}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            if "command not found" in result.stderr:
                return "Docker не установлен"
            elif "Cannot connect" in result.stderr:
                return "Docker не запущен"
            else:
                return f"Ошибка Docker: {result.stderr.strip()[:100]}"

        containers = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("|")
                if len(parts) >= 5:
                    name = parts[0]
                    container_id = parts[1]
                    cpu_percent = parts[2].strip() or "-"
                    mem_usage = parts[3].strip() or "-"
                    mem_percent = parts[4].strip() or "-"

                    container_info = f"• {name} ({container_id}), CPU: {cpu_percent}, RAM: {mem_usage} ({mem_percent})"
                    containers.append(container_info)

        if not containers:
            return "Нет работающих контейнеров"

        return "\n".join(containers)

    except subprocess.TimeoutExpired:
        return "Таймаут запроса к Docker"
    except Exception as e:
        logger.error(f"Ошибка при получении Docker контейнеров: {e}")
        return f"Ошибка получения статистики"


async def main(tgkey=None, chatID=None):
    """Основная функция для формирования системного отчета"""
    try:
        # Базовая информация о системе
        uname = platform.uname()

        # Время загрузки и аптайм
        try:
            boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.datetime.now() - boot_time
            boot_time_str = boot_time.strftime("%Y-%m-%d %H:%M:%S")
            uptime_str = format_uptime(uptime)
        except Exception as e:
            logger.error(f"Ошибка при получении времени загрузки: {e}")
            boot_time_str = "N/A"
            uptime_str = "N/A"

        # CPU
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_str = f"{cpu_percent:.1f}%"
        except Exception as e:
            logger.error(f"Ошибка при получении нагрузки CPU: {e}")
            cpu_str = "N/A"

        # Память
        try:
            mem = psutil.virtual_memory()
            mem_percent = f"{mem.percent:.1f}%"
            mem_used = bytes_to_human_readable(mem.used)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о памяти: {e}")
            mem_percent = "N/A"
            mem_used = "N/A"

        try:
            swap = psutil.swap_memory()
            swap_percent = f"{swap.percent:.1f}%" if swap.percent else "N/A"
            swap_used = (
                bytes_to_human_readable(swap.used) if hasattr(swap, "used") else "N/A"
            )
        except Exception as e:
            logger.error(f"Ошибка при получении информации о swap: {e}")
            swap_percent = "N/A"
            swap_used = "N/A"

        # Диск
        try:
            disk = psutil.disk_usage("/")
            disk_percent = f"{disk.percent:.1f}%"
            disk_used = bytes_to_human_readable(disk.used)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о диске: {e}")
            disk_percent = "N/A"
            disk_used = "N/A"

        # Сеть
        net_usage = "N/A"
        try:
            net1 = psutil.net_io_counters()
            await asyncio.sleep(1)
            net2 = psutil.net_io_counters()
            bytes_sent = net2.bytes_sent - net1.bytes_sent
            bytes_recv = net2.bytes_recv - net1.bytes_recv
            net_usage = f"⬆️ {bytes_to_human_readable(bytes_sent)}/s | ⬇️ {bytes_to_human_readable(bytes_recv)}/s"
        except Exception as e:
            logger.error(f"Ошибка при получении сетевой статистики: {e}")

        # Docker контейнеры
        docker_info = await get_docker_containers()

        # Проверка состояния системы
        alerts = []
        if isinstance(cpu_percent, (int, float)) and cpu_percent > 85:
            alerts.append("⚠️ Высокая нагрузка CPU")
        if isinstance(mem.percent, (int, float)) and mem.percent > 90:
            alerts.append("⚠️ Критическое использование RAM")
        if isinstance(disk.percent, (int, float)) and disk.percent > 90:
            alerts.append("⚠️ Мало места на диске")

        alert_text = "\n".join(alerts) if alerts else "✅ Система в норме"

        # Процессы
        proc_info = "Не удалось получить информацию о процессах"
        try:
            # Инициализируем CPU проценты
            for p in psutil.process_iter():
                try:
                    p.cpu_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            await asyncio.sleep(0.5)

            processes = []
            for p in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent"]
            ):
                try:
                    processes.append(p)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Сортируем по использованию CPU
            top_procs = sorted(
                processes, key=lambda x: x.info["cpu_percent"] or 0, reverse=True
            )[:5]

            proc_lines = []
            for p in top_procs:
                name = escape_html(p.info["name"][:20])
                pid = escape_html(str(p.info["pid"]))
                cpu = f"{p.info['cpu_percent'] or 0:.1f}"
                memory = f"{p.info['memory_percent'] or 0:.1f}"

                proc_lines.append(
                    f"— {name:<20} (PID {pid:>6}) CPU: {cpu:>5}% RAM: {memory:>5}%"
                )

            proc_info = "\n".join(proc_lines)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о процессах: {e}")

        # Сервисы
        services_to_check = ["ssh", "nginx", "docker"]
        services_status = "\n".join(check_service(s) for s in services_to_check)

        # Экранирование данных
        hostname = escape_html(uname.node)
        os_info = escape_html(f"{uname.system} {uname.release}")
        docker_info_escaped = escape_html(docker_info)
        services_status_escaped = escape_html(services_status)
        alert_text_escaped = escape_html(alert_text)
        proc_info_escaped = escape_html(proc_info)

        # Формирование сообщения
        message = (
            "🖥️ <b>Отчет о состоянии сервера</b>\n"
            "========================\n"
            f"• Хост: <code>{hostname}</code>\n"
            f"• ОС: <code>{os_info}</code>\n"
            f"• Загрузка: <code>{boot_time_str}</code>\n"
            f"• Аптайм: <code>{uptime_str}</code>\n"
            "------------------------\n"
            f"<b>CPU</b>: <code>{cpu_str}</code>\n"
            f"<b>RAM</b>: <code>{mem_percent}</code> ({mem_used})\n"
            f"<b>Swap</b>: <code>{swap_percent}</code> ({swap_used})\n"
            f"<b>Диск</b>: <code>{disk_percent}</code> ({disk_used})\n"
            f"<b>Сеть</b>: {net_usage}\n"
            "------------------------\n"
            f"<b>Статус:</b>\n{alert_text_escaped}\n"
            "------------------------\n"
            f"<b>Процессы:</b>\n"
            f"{proc_info_escaped}\n"
            "------------------------\n"
            f"<b>Сервисы:</b>\n"
            f"{services_status_escaped}\n"
            "------------------------\n"
            f"<b>Docker контейнеры:</b>\n"
            f"{docker_info_escaped}\n"
            "========================"
        )

        logger.info("Системный отчет успешно сформирован")
        return message

    except Exception as e:
        logger.error(f"Ошибка при формировании системного отчета: {e}")
        return "❌ Ошибка при формировании отчёта"


if __name__ == "__main__":
    asyncio.run(main())
