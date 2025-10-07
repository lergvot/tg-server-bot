# system_report.py
import asyncio
import datetime
import logging
import platform
import subprocess

import psutil

logger = logging.getLogger("system_report")

SYSTEMCTL_PATH = "/usr/bin/systemctl"  # which systemctl


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

        # Перевод статусов на русский
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
                "{{.Name}}|{{.Container}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.RunningFor}}",
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
                return f"Ошибка Docker stats: {result.stderr.strip()}"

        containers = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("|")
                if len(parts) >= 6:
                    name = parts[0]
                    container_id = parts[1]
                    cpu_percent = parts[2].strip()
                    mem_usage = parts[3].strip()
                    mem_percent = parts[4].strip()
                    running_for = parts[5].strip()

                    # Форматируем вывод
                    container_info = f"• {name} ({container_id}), CPU: {cpu_percent}, RAM: {mem_usage} ({mem_percent}), {running_for}"
                    containers.append(container_info)

        if not containers:
            return "Нет работающих контейнеров"

        return "\n".join(containers)

    except subprocess.TimeoutExpired:
        return "Таймаут запроса к Docker stats. Попробуйте снова."
    except Exception as e:
        logger.error(f"Ошибка при получении Docker контейнеров: {e}")
        return f"Ошибка получения статистики: {str(e)}\nПопробуйте повторить запрос."


async def main(tgkey=None, chatID=None):
    """Основная функция для формирования системного отчета"""
    try:
        # Получение базовой информации о системе
        uname = platform.uname()

        # Получение времени загрузки и аптайма
        try:
            boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.datetime.now() - boot_time
        except Exception as e:
            logger.error(f"Ошибка при получении времени загрузки: {e}")
            boot_time = "N/A"
            uptime = "N/A"

        # Получение информации о CPU
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
        except Exception as e:
            logger.error(f"Ошибка при получении нагрузки CPU: {e}")
            cpu_percent = "N/A"

        # Получение информации о памяти
        try:
            mem = psutil.virtual_memory()
        except Exception as e:
            logger.error(f"Ошибка при получении информации о памяти: {e}")
            mem = type("obj", (object,), {"percent": "N/A", "used": 0})()

        try:
            swap = psutil.swap_memory()
        except Exception as e:
            logger.error(f"Ошибка при получении информации о swap: {e}")
            swap = type("obj", (object,), {"percent": "N/A", "used": 0})()

        # Получение информации о диске
        try:
            disk = psutil.disk_usage("/")
        except Exception as e:
            logger.error(f"Ошибка при получении информации о диске: {e}")
            disk = type("obj", (object,), {"percent": "N/A", "used": 0})()

        # Получение сетевой статистики
        net_usage = "N/A"
        try:
            net1 = psutil.net_io_counters()
            await asyncio.sleep(1)
            net2 = psutil.net_io_counters()
            bytes_sent = net2.bytes_sent - net1.bytes_sent
            bytes_recv = net2.bytes_recv - net1.bytes_recv
            net_usage = (
                f"⬆️ {bytes_to_human_readable(bytes_sent)}/s | "
                f"⬇️ {bytes_to_human_readable(bytes_recv)}/s"
            )
        except Exception as e:
            logger.error(f"Ошибка при получении сетевой статистики: {e}")

        # Получаем информацию о Docker контейнерах
        docker_info = await get_docker_containers()

        # Проверка состояния системы
        alerts = []
        if isinstance(cpu_percent, (int, float)) and cpu_percent > 85:
            alerts.append("⚠️ Высокая нагрузка CPU!")
        if isinstance(mem.percent, (int, float)) and mem.percent > 90:
            alerts.append("⚠️ Критическое использование RAM!")
        if isinstance(disk.percent, (int, float)) and disk.percent > 90:
            alerts.append("⚠️ Мало места на диске!")

        alert_text = "\n".join(alerts) if alerts else "✅ Система в норме"

        # Получение информации о процессах
        proc_info = "Не удалось получить информацию о процессах"
        try:
            for p in psutil.process_iter():
                try:
                    p.cpu_percent(interval=None)
                except Exception:
                    pass
            await asyncio.sleep(1)
            procs = []
            for p in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent"]
            ):
                try:
                    procs.append(p)
                except Exception:
                    pass
            top_procs = sorted(
                procs, key=lambda p: p.info["cpu_percent"], reverse=True
            )[:5]

            proc_info = "\n".join(
                f"— *{p.info['name']:<20}* "  # имя процесса, выравнивание по левому краю, 20 символов
                f"(PID `{p.info['pid']:>5}`)  "  # PID, выравнивание по правому краю, 5 символов
                f"CPU: `{p.info['cpu_percent']:>5.1f}%`  "  # CPU, выравнивание по правому краю, 5 символов
                f"RAM: `{p.info['memory_percent']:>5.1f}%`"  # RAM, выравнивание по правому краю, 5 символов
                for p in top_procs
            )
        except Exception as e:
            logger.error(f"Ошибка при получении информации о процессах: {e}")

        # Проверка статуса сервисов
        services_to_check = ["ssh", "nginx", "docker"]
        services_status = "\n".join(check_service(s) for s in services_to_check)

        # Формирование сообщения
        message = (
            "🖥️ *Отчет о состоянии сервера*\n"
            "========================\n"
            f"• Хост: `{uname.node}`\n"
            f"• ОС: `{uname.system} {uname.release}`\n"
            f"• Дата запуска: `{boot_time if isinstance(boot_time, str) else boot_time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"• Аптайм: `{uptime if isinstance(uptime, str) else format_uptime(uptime)}`\n"
            "------------------------\n"
            f"*CPU*: `{cpu_percent}%`\n"
            f"*RAM*: `{mem.percent if hasattr(mem, 'percent') else 'N/A'}%` "
            f" ({bytes_to_human_readable(mem.used) if hasattr(mem, 'used') else 'N/A'})\n"
            f"*Swap*: `{swap.percent if hasattr(swap, 'percent') else 'N/A'}%` "
            f" ({bytes_to_human_readable(swap.used) if hasattr(swap, 'used') else 'N/A'})\n"
            f"*Диск*: `{disk.percent if hasattr(disk, 'percent') else 'N/A'}%` "
            f" ({bytes_to_human_readable(disk.used) if hasattr(disk, 'used') else 'N/A'})\n"
            f"*Сеть*: {net_usage}\n"
            "------------------------\n"
            f"*Статус:*\n{alert_text}\n"
            "------------------------\n"
            "*Процессы:*\n"
            f"{proc_info}\n"
            "------------------------\n"
            "*Сервисы:*\n"
            f"{services_status}\n"
            "------------------------\n"
            "*Docker контейнеры:*\n"
            f"{docker_info}\n"
            "========================"
        )
        logger.info("Системный отчет успешно сформирован.")
        return message

    except Exception as e:
        logger.error(f"Ошибка при формировании системного отчета: {e}")
        return "❌ Ошибка при формировании отчёта."


if __name__ == "__main__":
    asyncio.run(main())
