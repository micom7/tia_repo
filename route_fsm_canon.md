# Route FSM — канон (PLC L3 Route Supervisor)

Формат таблиці: **(Стан) → Подія/Умова → Дія PLC → Наступний стан → ResultCode/Примітка**

## Канон (зафіксовано)
- **Без PAUSE**
- **Будь-який Fault = аварія**
- **STOP_SAFETY** — негайний (жорсткий)  
- **STOP_OPERATOR** — контрольований
- Після **ABORTED_\*** — **owner release одразу**
- Повторний **START** = **новий запуск**
- Дубль **START** по тому ж **RouteId** → **REJECT**
- **START**, поки маршрут не завершився → **ігнор**

---

## 0) Список станів Route FSM

- `IDLE` (початковий)
- `VALIDATING`
- `LOCKING`
- `STARTING`
- `RUNNING`
- `STOPPING` (контрольована зупинка)
- `DONE` (фінальний)
- `REJECTED` (фінальний)
- `ABORTED` (фінальний)

> `ABORTED` має підпричину в `ResultCode` (SAFETY/LOCAL/FAULT/OPERATOR).

---

## 1) Події (вхідні тригери)

- `E_START` — SCADA старт маршруту (commit)
- `E_STOP_OP` — SCADA “простий Stop” маршруту (контрольований)
- `E_SAFETY_STOP` — `GlobalSafetyStop=1` (SCADA safety-stop OR апаратна кнопка)
- `E_LOCAL_MANUAL` — `LocalManualGlobal=1` або `M.LocalManual=1` (під час RUNNING/STARTING)
- `E_FAULT_ANY` — будь-який `FLTCode != 0` на будь-якому slot маршруту
- `E_ALL_STARTED` — всі потрібні механізми підтвердили `RUNNING/READY`
- `E_ALL_STOPPED` — всі механізми зупинені (feedback/статус)
- `E_DUP_START` — повторний START по тому ж RouteId
- `E_BUSY_START` — START прийшов, коли маршрут не завершився

---

## 2) ResultCode (мінімальний набір)

### REJECT
- `REJ_BY_SAFETY`
- `REJ_BY_OWNER` (owner≠0 на будь-якому slot)
- `REJ_BY_CONTRACT` (slot/type/структура невалідні)
- `REJ_NOT_READY` (Enable_OK=0 / LocalManual=1 / interlocks/HAL not OK / blocked)
- `REJ_DUPLICATE_START` (той самий RouteId)

### ABORT
- `ABORT_BY_OPERATOR`
- `ABORT_BY_SAFETY`
- `ABORT_BY_LOCAL`
- `ABORT_BY_FAULT`
- `ABORT_STARTING_FAILED` (не повинно статись, але є “страховка”)

### DONE
- `DONE_OK`

> `ResultCode` фіксується у фінальних станах і **очищається лише при новому START** цього RouteId.

---

## 3) Таблиця станів Route FSM

### A) Глобальні правила (діють з будь-якого стану)

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| будь-який | `E_SAFETY_STOP` (`GlobalSafetyStop=1`) | Негайно STOP всіх керованих виходів (global); маршрут → abort; release owner одразу | `ABORTED` | `ABORT_BY_SAFETY` |
| будь-який | `E_START` при `GlobalSafetyStop=1` | не лочити, не стартувати | `REJECTED` | `REJ_BY_SAFETY` |

> Негайний STOP — це “жорсткий” режим (без чекання, без послідовностей).

---

### B) IDLE

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `IDLE` | `E_START` | прийняти запит (route payload), перейти до перевірок | `VALIDATING` | — |

---

### C) VALIDATING

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `VALIDATING` | `E_DUP_START` (другий START того ж RouteId) | не робити side-effects | `REJECTED` | `REJ_DUPLICATE_START` |
| `VALIDATING` | будь-який slot owner≠0 | не лочити | `REJECTED` | `REJ_BY_OWNER` |
| `VALIDATING` | помилка контракту (slot не існує / type mismatch / формат) | не лочити | `REJECTED` | `REJ_BY_CONTRACT` |
| `VALIDATING` | не готовий (Enable_OK=0 або LocalManual=1 або HAL/Safety interlock не OK) | не лочити | `REJECTED` | `REJ_NOT_READY` |
| `VALIDATING` | все ок | готувати atomic lock | `LOCKING` | — |

> Тут реалізується вимога: “такого не повинно статись під час STARTING” — **вся готовність перевіряється до пуску**.

---

### D) LOCKING

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `LOCKING` | atomic lock успішний | OwnerCur := ROUTE, OwnerCurId := RouteId для всіх slot | `STARTING` | — |
| `LOCKING` | lock не вдався (race: owner змінився) | не частково, все відкатити/не ставити | `REJECTED` | `REJ_BY_OWNER` |

---

### E) STARTING

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `STARTING` | `E_STOP_OP` | перейти на контрольовану зупинку того, що вже стартувало | `STOPPING` | `ABORT_BY_OPERATOR` (фіксується по завершенню зупинки) |
| `STARTING` | `E_LOCAL_MANUAL` | контрольований STOP | `STOPPING` | `ABORT_BY_LOCAL` |
| `STARTING` | `E_FAULT_ANY` | контрольований STOP | `STOPPING` | `ABORT_BY_FAULT` |
| `STARTING` | механізм “не може стартувати” (страховка) | контрольований STOP | `STOPPING` | `ABORT_STARTING_FAILED` |
| `STARTING` | `E_ALL_STARTED` | перейти в робочий режим | `RUNNING` | — |

> У STARTING **немає очікування таймаутів** у канон-версії.

---

### F) RUNNING

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `RUNNING` | `E_STOP_OP` | контрольований STOP всіх механізмів маршруту (у правильній послідовності) | `STOPPING` | `ABORT_BY_OPERATOR` |
| `RUNNING` | `E_LOCAL_MANUAL` | контрольований STOP | `STOPPING` | `ABORT_BY_LOCAL` |
| `RUNNING` | `E_FAULT_ANY` | контрольований STOP | `STOPPING` | `ABORT_BY_FAULT` |
| `RUNNING` | (умова завершення маршруту, якщо є) | контрольований STOP або “все вже зупинено” | `DONE` або `STOPPING→DONE` | `DONE_OK` |

---

### G) STOPPING (контрольована зупинка)

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `STOPPING` | `E_ALL_STOPPED` | release owner одразу; зафіксувати ResultCode (який був вибраний при вході в STOPPING) | `ABORTED` або `DONE` | `ABORT_*` або `DONE_OK` |
| `STOPPING` | `E_SAFETY_STOP` (якщо раптом з’явився) | негайний STOP + release owner | `ABORTED` | `ABORT_BY_SAFETY` |

---

### H) Фінальні стани: DONE / REJECTED / ABORTED

| Поточний стан | Подія/умова | Дія PLC | Наступний стан | ResultCode/Примітка |
|---|---|---|---|---|
| `DONE/REJECTED/ABORTED` | `E_BUSY_START` (START коли маршрут ще не “повернутий у IDLE”) | ігнорувати | без змін | — |
| `DONE/REJECTED/ABORTED` | “маршрут завершений” + внутрішня логіка циклу | маршрут готовий до нового циклу | `IDLE` | зберігати result до нового START |

> Ти сказав: “якщо маршрут ABORTED_, то всі механізми вільні, це початковий стан”.  
Тому практично: `ABORTED` після release owner можна трактувати як готовність до `IDLE` (але `ResultCode` лишається в статусі до нового START).

---

## 4) Мінімальний набір полів, щоб SCADA не гадала

Для кожного `RouteId` у PLC достатньо:

- `State` (enum)
- `ResultCode` (enum)
- `Active` (bool або похідне `State ∈ {VALIDATING..STOPPING}`)
- `LastTransitionTick/Time` (не обов’язково, але зручно)
- `OwnerSnapshot` (опційно для журналу)
