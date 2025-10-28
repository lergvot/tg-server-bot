# system_report.py
import asyncio
import datetime
import html
import logging
import os
import platform
import re
import subprocess
from collections import defaultdict

logger = logging.getLogger("system_report")

SYSTEMCTL_PATH = "/usr/bin/systemctl"

HOST_PROC_PATH = "/host/proc"
HOST_SYS_PATH = "/host/sys"
HOST_ROOT_PATH = "/host_root"  # Для disk_usage


def read_load_average():
    """Читает среднюю загрузку системы из /host/proc/loadavg."""
    try:
        with open(os.path.join(HOST_PROC_PATH, "loadavg"), "r") as f:
            parts = f.read().strip().split()
            if len(parts) >= 3:
                return {
                    "1min": float(parts[0]),
                    "5min": float(parts[1]),
                    "15min": float(parts[2]),
                }
    except FileNotFoundError:
        logger.error(f"Файл {os.path.join(HOST_PROC_PATH, 'loadavg')} не найден")
    except Exception as e:
        logger.error(f"Ошибка при чтении loadavg: {e}")
    return {"1min": 0.0, "5min": 0.0, "15min": 0.0}


def read_cpu_count():
    """Получает количество CPU ядер."""
    try:
        with open(os.path.join(HOST_PROC_PATH, "cpuinfo"), "r") as f:
            cpu_count = sum(1 for line in f if line.startswith("processor"))
            return cpu_count if cpu_count > 0 else os.cpu_count() or 1
    except Exception as e:
        logger.error(f"Ошибка при чтении cpuinfo: {e}")
        return os.cpu_count() or 1


def read_cpu_temperature():
    """Пытается прочитать температуру CPU из различных источников."""
    temp_sources = [
        # Intel/AMD common paths
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
        "/host/sys/devices/virtual/thermal/thermal_zone0/temp",
        # AMD specific
        "/sys/class/hwmon/hwmon0/temp1_input",
        "/host/sys/class/hwmon/hwmon0/temp1_input",
        # Raspberry Pi
        "/sys/class/thermal/thermal_zone0/temp",
        "/host/sys/class/thermal/thermal_zone0/temp",
    ]

    for path in temp_sources:
        try:
            with open(path, "r") as f:
                temp_mc = int(f.read().strip())
                # Температура обычно в миллиградусах Цельсия
                temp_c = temp_mc / 1000.0
                return f"{temp_c:.1f}°C"
        except (FileNotFoundError, ValueError, OSError):
            continue

    return None


def read_cpu_stats():
    """Читает /host/proc/stat и возвращает информацию о CPU."""
    cpu_times = {}
    try:
        with open(os.path.join(HOST_PROC_PATH, "stat"), "r") as f:
            for line in f:
                if line.startswith("cpu "):  # Общее значение
                    parts = line.split()
                    cpu_times["total"] = sum(int(x) for x in parts[1:8])
                    cpu_times["idle"] = int(parts[4])
                    break
    except FileNotFoundError:
        logger.error(f"Файл {os.path.join(HOST_PROC_PATH, 'stat')} не найден")
    except Exception as e:
        logger.error(f"Ошибка при чтении {os.path.join(HOST_PROC_PATH, 'stat')}: {e}")
    return cpu_times


def read_memory_stats():
    """Читает /host/proc/meminfo и возвращает информацию о памяти."""
    mem_info = {}
    try:
        with open(os.path.join(HOST_PROC_PATH, "meminfo"), "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_info["total"] = int(line.split()[1]) * 1024  # KiB to bytes
                elif line.startswith("MemFree:"):
                    mem_info["free"] = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    mem_info["available"] = int(line.split()[1]) * 1024
                elif line.startswith("Buffers:"):
                    mem_info["buffers"] = int(line.split()[1]) * 1024
                elif line.startswith("Cached:"):
                    mem_info["cached"] = int(line.split()[1]) * 1024
                elif line.startswith("SwapTotal:"):
                    mem_info["swap_total"] = int(line.split()[1]) * 1024
                elif line.startswith("SwapFree:"):
                    mem_info["swap_free"] = int(line.split()[1]) * 1024
                # Останавливаемся, когда нашли все нужные поля
                if all(
                    k in mem_info
                    for k in [
                        "total",
                        "free",
                        "available",
                        "buffers",
                        "cached",
                        "swap_total",
                        "swap_free",
                    ]
                ):
                    break
    except FileNotFoundError:
        logger.error(f"Файл {os.path.join(HOST_PROC_PATH, 'meminfo')} не найден")
    except Exception as e:
        logger.error(
            f"Ошибка при чтении {os.path.join(HOST_PROC_PATH, 'meminfo')}: {e}"
        )
    return mem_info


def read_disk_stats(path="/"):
    """Читает информацию о диске для указанного пути."""
    try:
        # Используем HOST_ROOT_PATH как корень для пути
        full_path = os.path.join(HOST_ROOT_PATH, path.lstrip("/"))
        statvfs = os.statvfs(full_path)
        total = statvfs.f_frsize * statvfs.f_blocks
        free = statvfs.f_frsize * statvfs.f_bavail
        used = total - free
        percent = (used / total) * 100 if total > 0 else 0
        return {"total": total, "used": used, "free": free, "percent": percent}
    except Exception as e:
        logger.error(f"Ошибка при получении статистики диска для {full_path}: {e}")
        return {"total": 0, "used": 0, "free": 0, "percent": 0}


def read_disk_io():
    """Читает I/O статистику дисков из /host/proc/diskstats."""
    disk_io = {}
    try:
        with open(os.path.join(HOST_PROC_PATH, "diskstats"), "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 14:
                    device = parts[2]
                    if not device.startswith("loop") and not device.startswith("ram"):
                        read_sectors = int(parts[5])
                        write_sectors = int(parts[9])
                        disk_io[device] = {
                            "read_sectors": read_sectors,
                            "write_sectors": write_sectors,
                        }
    except FileNotFoundError:
        logger.error(f"Файл {os.path.join(HOST_PROC_PATH, 'diskstats')} не найден")
    except Exception as e:
        logger.error(f"Ошибка при чтении diskstats: {e}")
    return disk_io


def read_network_stats():
    """Читает /host/proc/net/dev и возвращает информацию о сети."""
    net_info = {}
    try:
        with open(os.path.join(HOST_PROC_PATH, "net/dev"), "r") as f:
            lines = f.readlines()[2:]  # Пропускаем заголовки
            for line in lines:
                parts = line.split()
                if len(parts) >= 10:
                    interface = parts[0].rstrip(":")
                    bytes_recv = int(parts[1])
                    bytes_sent = int(parts[9])
                    net_info[interface] = {
                        "bytes_recv": bytes_recv,
                        "bytes_sent": bytes_sent,
                    }
    except FileNotFoundError:
        logger.error(f"Файл {os.path.join(HOST_PROC_PATH, 'net/dev')} не найден")
    except Exception as e:
        logger.error(
            f"Ошибка при чтении {os.path.join(HOST_PROC_PATH, 'net/dev')}: {e}"
        )
    return net_info


def read_boot_time():
    """Читает время загрузки из /host/proc/stat."""
    boot_time = 0
    try:
        with open(os.path.join(HOST_PROC_PATH, "stat"), "r") as f:
            for line in f:
                if line.startswith("btime "):
                    boot_time = int(line.split()[1])
                    break
    except FileNotFoundError:
        logger.error(f"Файл {os.path.join(HOST_PROC_PATH, 'stat')} не найден для btime")
    except Exception as e:
        logger.error(
            f"Ошибка при чтении btime из {os.path.join(HOST_PROC_PATH, 'stat')}: {e}"
        )
    return boot_time


def read_processes_with_stats():
    """
    Читает информацию о процессах из /host/proc/[pid].
    Возвращает список словарей с PID, именем, utime+stime (для CPU) и vsize/rss (для RAM).
    """
    processes = []
    try:
        for pid_dir in os.listdir(os.path.join(HOST_PROC_PATH)):
            if pid_dir.isdigit():
                pid = int(pid_dir)
                try:
                    with open(os.path.join(HOST_PROC_PATH, str(pid), "comm"), "r") as f:
                        name = f.read().strip()
                    # Читаем /host/proc/[pid]/stat для вычисления CPU%
                    with open(os.path.join(HOST_PROC_PATH, str(pid), "stat"), "r") as f:
                        stat_line = f.read().strip()
                        stat_parts = stat_line.split()
                        # utime (14-е поле, индекс 13) + stime (15-е поле, индекс 14)
                        # В тиках CPU
                        utime = int(stat_parts[13]) if len(stat_parts) > 14 else 0
                        stime = int(stat_parts[14]) if len(stat_parts) > 15 else 0
                        total_time = utime + stime

                    # Читаем /host/proc/[pid]/status для вычисления RAM%
                    vsize = 0  # Virtual memory size in bytes
                    rss = 0  # Resident Set Size in pages
                    with open(
                        os.path.join(HOST_PROC_PATH, str(pid), "status"), "r"
                    ) as f:
                        for status_line in f:
                            if status_line.startswith("VmSize:"):
                                vsize = (
                                    int(status_line.split()[1]) * 1024
                                )  # KiB to bytes
                            elif status_line.startswith("VmRSS:"):
                                rss = int(status_line.split()[1]) * 1024  # KiB to bytes
                            # Прерываем, если нашли оба значения
                            if vsize > 0 and rss > 0:
                                break

                    processes.append(
                        {
                            "pid": pid,
                            "name": name,
                            "total_time": total_time,
                            "vsize": vsize,
                            "rss": rss,
                        }
                    )
                except (
                    FileNotFoundError,
                    PermissionError,
                    OSError,
                    IndexError,
                    ValueError,
                ):
                    # Процесс мог завершиться, быть недоступен или stat/status файл имеет неожиданный формат
                    continue
    except FileNotFoundError:
        logger.error(f"Директория {os.path.join(HOST_PROC_PATH)} не найдена")
    except Exception as e:
        logger.error(
            f"Ошибка при чтении процессов из {os.path.join(HOST_PROC_PATH)}: {e}"
        )
    return processes


def calculate_process_cpu_percent(
    prev_processes, current_processes, cpu_time_diff_ticks
):
    """
    Вычисляет процент использования CPU процессами.
    cpu_time_diff_ticks - разница в общем времени CPU за интервал.
    """
    process_cpu_percentages = {}
    if cpu_time_diff_ticks <= 0:
        # Если время CPU не изменилось, нагрузка 0
        for p in current_processes:
            process_cpu_percentages[p["pid"]] = 0.0
        return process_cpu_percentages

    # Учтём количество ядер
    cpu_count = os.cpu_count() or 1
    for current_p in current_processes:
        pid = current_p["pid"]
        # Найти предыдущее значение для этого PID
        prev_p = next((p for p in prev_processes if p["pid"] == pid), None)
        if prev_p:
            time_diff = current_p["total_time"] - prev_p["total_time"]
            # Формула: (разница_времени_процесса / разница_общего_времени_цпу) * 100 * число_ядер
            cpu_percent = (time_diff / cpu_time_diff_ticks) * 100.0 * cpu_count
            process_cpu_percentages[pid] = max(
                0.0, cpu_percent
            )  # Не отрицательное значение
        else:
            # Процесс появился во втором замере, нагрузка неопределена или 0
            process_cpu_percentages[pid] = 0.0

    return process_cpu_percentages


def calculate_process_memory_percent(processes, total_memory_bytes):
    """
    Вычисляет процент использования RAM процессами.
    total_memory_bytes - общее количество памяти хоста.
    """
    process_memory_percentages = {}
    for p in processes:
        pid = p["pid"]
        rss = p["rss"]  # Используем RSS (резидентную память)
        if total_memory_bytes > 0:
            mem_percent = (rss / total_memory_bytes) * 100.0
        else:
            mem_percent = 0.0
        process_memory_percentages[pid] = mem_percent
    return process_memory_percentages


def calculate_cpu_percent(prev_cpu_times, current_cpu_times):
    """Вычисляет процент использования CPU на основе двух замеров."""
    if not prev_cpu_times or not current_cpu_times:
        return 0.0

    total_diff = current_cpu_times["total"] - prev_cpu_times["total"]
    idle_diff = current_cpu_times["idle"] - prev_cpu_times["idle"]

    if total_diff == 0:
        return 0.0

    cpu_percent = (total_diff - idle_diff) / total_diff * 100.0
    return cpu_percent


def calculate_network_speed(prev_net, current_net):
    """Вычисляет скорость передачи данных."""
    speeds = {}
    for interface, current_data in current_net.items():
        if interface in prev_net:
            bytes_sent_diff = (
                current_data["bytes_sent"] - prev_net[interface]["bytes_sent"]
            )
            bytes_recv_diff = (
                current_data["bytes_recv"] - prev_net[interface]["bytes_recv"]
            )
            # Скорость за 1 секунду (asyncio.sleep(1) в основном коде)
            speeds[interface] = {
                "bytes_sent_per_sec": bytes_sent_diff,
                "bytes_recv_per_sec": bytes_recv_diff,
            }
    return speeds


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
    """Получаем информацию о работающих Docker контейнерах, группируем по проекту"""
    try:
        import docker

        # Подключаемся к Docker daemon через socket
        try:
            client = docker.from_env()
            # Проверяем подключение
            client.ping()
        except Exception as e:
            return f"Docker недоступен: {str(e)[:50]}"

        try:
            # Получаем все работающие контейнеры
            containers = client.containers.list()

            if not containers:
                return "Нет работающих контейнеров"

            # Группируем контейнеры по имени проекта (до первого _)
            grouped_containers = defaultdict(list)

            for container in containers:
                name = container.name
                container_id = container.short_id

                # Извлекаем имя проекта из имени контейнера
                project_match = re.match(r"^([a-zA-Z0-9_-]+)_", name)
                project_name = project_match.group(1) if project_match else "default"

                # Получаем статистику контейнера
                try:
                    stats = container.stats(stream=False)

                    # Вычисляем CPU процент
                    cpu_stats = stats["cpu_stats"]
                    precpu_stats = stats["precpu_stats"]

                    cpu_delta = (
                        cpu_stats["cpu_usage"]["total_usage"]
                        - precpu_stats["cpu_usage"]["total_usage"]
                    )
                    system_delta = (
                        cpu_stats["system_cpu_usage"] - precpu_stats["system_cpu_usage"]
                    )

                    if system_delta > 0 and cpu_delta > 0:
                        cpu_percent = (
                            (cpu_delta / system_delta)
                            * len(cpu_stats["cpu_usage"]["percpu_usage"])
                            * 100.0
                        )
                        cpu_str = f"{cpu_percent:.1f}%"
                    else:
                        cpu_str = "0.0%"

                    # Вычисляем память
                    mem_usage = stats["memory_stats"]["usage"]
                    mem_limit = stats["memory_stats"]["limit"]
                    mem_percent = (
                        (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0
                    )

                    mem_usage_str = bytes_to_human_readable(mem_usage)
                    mem_limit_str = bytes_to_human_readable(mem_limit)
                    mem_str = f"{mem_usage_str} / {mem_limit_str}"
                    mem_percent_str = f"{mem_percent:.1f}%"

                except Exception:
                    cpu_str = "N/A"
                    mem_str = "N/A"
                    mem_percent_str = "N/A"

                container_info = f"• {name} ({container_id}), CPU: {cpu_str}, RAM: {mem_str} ({mem_percent_str})"
                grouped_containers[project_name].append(container_info)

            # Формируем строку отчёта
            report_lines = []
            for project, containers in grouped_containers.items():
                report_lines.append(f"<b>Проект '{project}':</b>")
                report_lines.extend(containers)

            return "\n".join(report_lines)

        finally:
            client.close()

    except ImportError:
        return "Docker библиотека недоступна"
    except Exception as e:
        logger.error(f"Ошибка при получении Docker контейнеров: {e}")
        return f"Ошибка получения статистики: {str(e)[:50]}"


async def main(tgkey=None, chatID=None):
    """Основная функция для формирования системного отчета"""
    try:
        # Базовая информация о системе
        uname = platform.uname()

        # Количество CPU ядер
        cpu_count = read_cpu_count()

        # Load average
        load_avg = read_load_average()

        # Температура CPU
        cpu_temp = read_cpu_temperature()

        # Время загрузки и аптайм (из /host/proc/stat)
        try:
            boot_time_timestamp = read_boot_time()
            if boot_time_timestamp > 0:
                boot_time = datetime.datetime.fromtimestamp(boot_time_timestamp)
                uptime = datetime.datetime.now() - boot_time
                boot_time_str = boot_time.strftime("%Y-%m-%d %H:%M:%S")
                uptime_str = format_uptime(uptime)
            else:
                boot_time_str = "N/A"
                uptime_str = "N/A"
        except Exception as e:
            logger.error(f"Ошибка при получении времени загрузки: {e}")
            boot_time_str = "N/A"
            uptime_str = "N/A"

        # CPU (из /host/proc/stat)
        try:
            # Первый замер
            prev_cpu_times = read_cpu_stats()
            await asyncio.sleep(1)
            # Второй замер
            current_cpu_times = read_cpu_stats()
            cpu_percent = calculate_cpu_percent(prev_cpu_times, current_cpu_times)
            cpu_str = f"{cpu_percent:.1f}%"
        except Exception as e:
            logger.error(f"Ошибка при получении нагрузки CPU: {e}")
            cpu_str = "N/A"

        # Память (из /host/proc/meminfo)
        try:
            mem_info = read_memory_stats()
            if mem_info:
                mem_total = mem_info.get("total", 0)
                mem_available = mem_info.get("available", 0)
                mem_used = (
                    mem_total
                    - mem_info.get("free", 0)
                    - mem_info.get("buffers", 0)
                    - mem_info.get("cached", 0)
                )
                # Или используем MemUsed = MemTotal - MemFree - Buffers - Cached
                # mem_used_calc = mem_info['total'] - mem_info['free'] - mem_info['buffers'] - mem_info['cached']
                mem_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0
                mem_percent_str = f"{mem_percent:.1f}%"
                mem_used_str = bytes_to_human_readable(mem_used)
            else:
                mem_percent_str = "N/A"
                mem_used_str = "N/A"
        except Exception as e:
            logger.error(f"Ошибка при получении информации о памяти: {e}")
            mem_percent_str = "N/A"
            mem_used_str = "N/A"

        try:
            # Swap (из /host/proc/meminfo)
            swap_total = mem_info.get("swap_total", 0)
            swap_free = mem_info.get("swap_free", 0)
            swap_used = swap_total - swap_free
            swap_percent = (swap_used / swap_total) * 100 if swap_total > 0 else 0
            swap_percent_str = f"{swap_percent:.1f}%"
            swap_used_str = bytes_to_human_readable(swap_used)
        except Exception as e:
            logger.error(f"Ошибка при получении информации о swap: {e}")
            swap_percent_str = "N/A"
            swap_used_str = "N/A"

        # Диск (из /host_root/)
        try:
            disk_info = read_disk_stats("/")  # Используем корень хоста
            disk_percent_str = f"{disk_info['percent']:.1f}%"
            disk_used_str = bytes_to_human_readable(disk_info["used"])
        except Exception as e:
            logger.error(f"Ошибка при получении информации о диске: {e}")
            disk_percent_str = "N/A"
            disk_used_str = "N/A"

        # Disk I/O
        try:
            prev_disk_io = read_disk_io()
            await asyncio.sleep(1)
            current_disk_io = read_disk_io()
            # Вычисляем разницу I/O
            total_read = 0
            total_write = 0
            for device in current_disk_io:
                if device in prev_disk_io:
                    read_diff = (
                        current_disk_io[device]["read_sectors"]
                        - prev_disk_io[device]["read_sectors"]
                    )
                    write_diff = (
                        current_disk_io[device]["write_sectors"]
                        - prev_disk_io[device]["write_sectors"]
                    )
                    # Секторы обычно по 512 байт
                    total_read += read_diff * 512
                    total_write += write_diff * 512
            disk_io_str = f"⬆️ {bytes_to_human_readable(total_write)}/s | ⬇️ {bytes_to_human_readable(total_read)}/s"
        except Exception as e:
            logger.error(f"Ошибка при получении I/O диска: {e}")
            disk_io_str = "N/A"

        # Сеть (из /host/proc/net/dev)
        net_usage = "N/A"
        try:
            # Первый замер
            prev_net = read_network_stats()
            await asyncio.sleep(1)
            # Второй замер
            current_net = read_network_stats()
            net_speeds = calculate_network_speed(prev_net, current_net)

            # Суммируем скорости по всем интерфейсам (кроме loopback)
            total_sent = 0
            total_recv = 0
            for interface, speeds in net_speeds.items():
                if interface != "lo":  # Пропускаем loopback
                    total_sent += speeds["bytes_sent_per_sec"]
                    total_recv += speeds["bytes_recv_per_sec"]

            net_usage = f"⬆️ {bytes_to_human_readable(total_sent)}/s | ⬇️ {bytes_to_human_readable(total_recv)}/s"
        except Exception as e:
            logger.error(f"Ошибка при получении сетевой статистики: {e}")

        # Docker контейнеры (группировка)
        docker_info = await get_docker_containers()

        # Проверка состояния системы
        alerts = []
        if isinstance(cpu_percent, (int, float)) and cpu_percent > 85:
            alerts.append("⚠️ Высокая нагрузка CPU")
        if load_avg["1min"] > cpu_count * 2:
            alerts.append(
                f"⚠️ Высокий load average ({load_avg['1min']:.2f} > {cpu_count * 2})"
            )
        if isinstance(mem_percent, (int, float)) and mem_percent > 90:
            alerts.append("⚠️ Критическое использование RAM")
        if isinstance(swap_percent, (int, float)) and swap_percent > 80:
            alerts.append("⚠️ Активное использование swap")
        if (
            isinstance(disk_info.get("percent"), (int, float))
            and disk_info["percent"] > 90
        ):
            alerts.append("⚠️ Мало места на диске")

        alert_text = "\n".join(alerts) if alerts else "✅ Система в норме"

        # Процессы (из /host/proc/[pid]) с CPU% и RAM%
        proc_info = "Не удалось получить информацию о процессах"
        try:
            # --- НОВАЯ ЛОГИКА ---
            # Первый замер времени процессов
            prev_processes = read_processes_with_stats()
            # Первый замер общего времени CPU для вычисления разницы
            prev_cpu_stats = read_cpu_stats()
            await asyncio.sleep(1)  # Ждём 1 секунду
            # Второй замер времени процессов
            current_processes = read_processes_with_stats()
            # Второй замер общего времени CPU
            current_cpu_stats = read_cpu_stats()

            # Вычисляем разницу общего времени CPU (в тиках)
            cpu_time_diff_ticks = current_cpu_stats["total"] - prev_cpu_stats["total"]

            # Вычисляем процент CPU для каждого процесса
            process_cpu_percentages = calculate_process_cpu_percent(
                prev_processes, current_processes, cpu_time_diff_ticks
            )

            # Вычисляем процент RAM для каждого процесса
            total_memory_bytes = mem_info.get("total", 0)
            process_memory_percentages = calculate_process_memory_percent(
                current_processes, total_memory_bytes
            )

            # Добавляем проценты в данные процессов
            for p in current_processes:
                p["cpu_percent"] = process_cpu_percentages.get(p["pid"], 0.0)
                p["memory_percent"] = process_memory_percentages.get(p["pid"], 0.0)

            # Сортируем по CPU% и RAM% отдельно
            top_procs_cpu = sorted(
                current_processes, key=lambda x: x["cpu_percent"], reverse=True
            )[:5]
            top_procs_mem = sorted(
                current_processes, key=lambda x: x["memory_percent"], reverse=True
            )[:5]

            proc_lines = []
            proc_lines.append("<b>По CPU:</b>")
            for p in top_procs_cpu:
                # Экранируем только имена процессов и PID
                name = escape_html(p["name"][:20])
                pid = escape_html(str(p["pid"]))
                cpu = f"{p['cpu_percent']:.1f}"
                memory = f"{p['memory_percent']:.1f}"
                proc_lines.append(
                    f"— {name:<20} (PID {pid:>6}) CPU: {cpu:>5}% RAM: {memory:>5}%"
                )

            proc_lines.append("\n<b>По RAM:</b>")
            for p in top_procs_mem:
                # Экранируем только имена процессов и PID
                name = escape_html(p["name"][:20])
                pid = escape_html(str(p["pid"]))
                cpu = f"{p['cpu_percent']:.1f}"
                memory = f"{p['memory_percent']:.1f}"
                proc_lines.append(
                    f"— {name:<20} (PID {pid:>6}) CPU: {cpu:>5}% RAM: {memory:>5}%"
                )

            proc_info = (
                "\n".join(proc_lines) if proc_lines else "Нет процессов для отображения"
            )
        except Exception as e:
            logger.error(f"Ошибка при получении информации о процессах: {e}")

        # Сервисы (пропускаем в контейнере - systemctl недоступен)
        try:
            services_to_check = ["ssh", "nginx", "docker"]
            services_status = "\n".join(check_service(s) for s in services_to_check)
        except Exception as e:
            logger.debug(f"Пропуск проверки сервисов: {e}")
            services_status = "N/A (контейнер без systemctl)"

        # Экранирование данных (proc_info не экранируем - там уже HTML и экранированы данные)
        hostname = escape_html(uname.node)
        os_info = escape_html(f"{uname.system} {uname.release}")
        docker_info_escaped = escape_html(docker_info)
        services_status_escaped = escape_html(services_status)
        alert_text_escaped = escape_html(alert_text)
        proc_info_escaped = proc_info  # Не экранируем - там уже HTML теги

        # Формирование сообщения
        temp_line = f"• Температура CPU: <code>{cpu_temp}</code>\n" if cpu_temp else ""
        message = (
            "🖥️ <b>Отчет о состоянии сервера</b>\n"
            "========================\n"
            f"• Хост: <code>{hostname}</code>\n"
            f"• ОС: <code>{os_info}</code>\n"
            f"• CPU ядер: <code>{cpu_count}</code>\n"
            f"• Средняя загрузка: <code>1m: {load_avg['1min']:.2f} | 5m: {load_avg['5min']:.2f} | 15m: {load_avg['15min']:.2f}</code>\n"
            f"{temp_line}"
            f"• Время запуска: <code>{boot_time_str}</code>\n"
            f"• Аптайм: <code>{uptime_str}</code>\n"
            "------------------------\n"
            f"<b>CPU</b>: <code>{cpu_str}</code>\n"
            f"<b>RAM</b>: <code>{mem_percent_str}</code> ({mem_used_str})\n"
            f"<b>Swap</b>: <code>{swap_percent_str}</code> ({swap_used_str})\n"
            f"<b>Диск</b>: <code>{disk_percent_str}</code> ({disk_used_str} из {bytes_to_human_readable(disk_info.get('total', 0))})\n"
            f"<b>Диск I/O</b>: {disk_io_str}\n"
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
