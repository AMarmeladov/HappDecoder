# Happ Decoder ++ — декодер VPN-подписок

Кроссплатформенная (Windows/Linux/macOS) программа на Python/Tkinter для расшифровки
подписок `happ://crypt…`, проверки серверов, экспорта конфигураций и заливки их
на OpenWrt-роутер (Podkop / NetShift).

<p align="center">
  <img width="720" alt="Расшифровка подписки" src="https://github.com/user-attachments/assets/3799f7c1-378f-4f1e-81c5-33fac450e976">
</p>
<p align="center">
  <img width="720" alt="Список серверов и проверка" src="https://github.com/user-attachments/assets/f9b19934-7684-48d6-b342-27be237e8aa7">
</p>
<p align="center">
  <img width="720" alt="Заливка на роутер" src="https://github.com/user-attachments/assets/e8bfb848-8655-4253-a3ef-cc449f518bde">
</p>

## Возможности

- **Расшифровка** ссылок `happ://add/…`, `happ://crypt3/…`, `happ://crypt4/…`, `happ://crypt5/…` (RSA-4096).
- **Протоколы:** VLESS, VMess, Trojan, Shadowsocks (+plugin), Hysteria2, TUIC, AnyTLS,
  ShadowTLS, NaïveProxy, Socks4/4a/5.
- **Маскировка клиента** как у реального приложения: Happ и INCY на Android / Android TV /
  iOS / macOS / Windows — точные `User-Agent`, `X-HWID`, `X-Device-OS`, `X-Ver-OS`,
  `X-Device-Model`, `X-Device-Locale`. Режимы HWID: случайный / в рамках сессии / свой.
- **Разбор ответов панелей:** Xray JSON, sing-box JSON, Clash/Mihomo YAML, Base64
  (std и url-safe), плюс перебор User-Agent'ов, если панель отдаёт разное разным клиентам.
- **Проверка доступности:** TCP/TLS-хендшейк, QUIC Initial, параллельно в 16 потоков.
- **Экспорт:**
  - sing-box **1.12+/1.14** — TUN `address`, `action: sniff` / `hijack-dns`, reality/utls,
    AnyTLS, Hysteria2 `server_ports` + `hop_interval`, fragment/noises;
  - Clash / Mihomo YAML;
  - QR-коды для каждого сервера.
- **OpenWrt по SSH:**
  - **Podkop 0.7.24** — `url` / `selector` / `urltest` / `outbound`;
  - **NetShift 0.9.12** — то же плюс текстовые блоки и режим
    **«подписка с HWID-подменой»** (`subscription_url` + `subscription_hwid`,
    `subscription_device_*`, `subscription_user_agent`, `subscription_update_interval`);
  - `failover_direct`, проверка журнала и процесса sing-box после перезапуска;
  - неподдерживаемые сервисом протоколы отбрасываются автоматически
    (Podkop: только vless/trojan/ss/socks4-5/hy2).

## Установка

Нужен Python 3.10+ (проверено на 3.14).

```bash
git clone https://github.com/<ваш-логин>/HappDecoder.git
cd HappDecoder
pip install -r requirements.txt
python happ_gui.py
```

Для проверки прокси через Tor дополнительно нужен локальный SOCKS5 (например, Tor Browser
или `tor`), но программа работает и без него.

## Сборка .exe

```bat
build.bat
```

Готовый файл появится в `dist\HappDecoder.exe`. Или вручную:

```bat
pyinstaller --onefile --windowed --name HappDecoder --icon icon.ico ^
  --collect-all curl_cffi --collect-all certifi happ_gui.py
```

## Как пользоваться (кратко)

1. **Декодер** — вставьте `happ://…` ссылку, при желании включите анонимный режим и
   выберите клиента (Happ/INCY), нажмите «▶ ПОЛУЧИТЬ ССЫЛКИ».
2. **Ссылки и проверка** — «⚡ Проверить доступность», отметьте живые, экспортируйте
   в sing-box / Clash / QR.
3. **Роутер** — введите IP и пароль SSH, «🔌 Подключиться», выберите секции и режим
   записи, «🚀 ЗАЛИТЬ В РОУТЕР». Для NetShift доступен режим подписки с подменой HWID
   и `failover_direct`.

Настройки (устройство, HWID, параметры роутера, геометрия окна) хранятся в
`%APPDATA%\HappDecoder` и не попадают в репозиторий.

## Совместимость

| Сервис | Версия | Режимы | Протоколы |
|---|---|---|---|
| NetShift | 0.9.12 | url, selector, urltest, *_text, subscription | vless, vmess, trojan, ss, hy2, tuic, anytls, socks, naive |
| Podkop | 0.7.24 | url, selector, urltest, outbound | vless, trojan, ss, socks4/5, hy2 |

## ⚠️ Дисклеймер

Программа предназначена для работы с **вашими собственными** подписками и серверами:
резервное копирование, миграция между клиентами, диагностика и настройка собственного
роутера. Автор не поддерживает использование для обхода оплаты, получения доступа к
чужим подпискам или нарушения условий обслуживания провайдеров. Ответственность за
использование лежит на пользователе. Проверяйте правила вашего провайдера и
законодательство вашей страны.

## Лицензия

GPL-2.0 — см. [LICENSE](LICENSE). Часть логики (генератор клиентской идентичности,
имена UCI-опций, набор заголовков) портирована из
[NetShift](https://github.com/yandexru45/netshift) (GPL-2.0), совместимость с
[Podkop](https://github.com/itdoginfo/podkop) (GPL-2.0).
Ключи расшифровки `crypt5` загружаются из [happ-decryptor](https://github.com/LeeeeT/happ-decryptor).
