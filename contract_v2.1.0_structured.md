# Універсальний контракт керування механізмами елеватора

**Версія:** v2.1.0 (Structured & Clarified)  
**Дата:** 2026-01-15  
**Базується на:** v2.0.0-system-contract  
**Статус:** ЗАТВЕРДЖЕНО

---

## 📋 Зміст

1. [Терміни та визначення](#1-терміни-та-визначення)
2. [Архітектура системи](#2-архітектура-системи)
3. [Контракт механізму](#3-контракт-механізму)
4. [Команди та стани](#4-команди-та-стани)
5. [Арбітраж та ownership](#5-арбітраж-та-ownership)
6. [Маршрути](#6-маршрути)
7. [Manual Control (ручне керування)](#7-manual-control-ручне-керування-зі-scada)
8. [Safety та інтерлоки](#8-safety-та-інтерлоки)
9. [Fault handling](#9-fault-handling)
10. [Розподіл відповідальності](#10-розподіл-відповідальності)
11. [Політики системи](#11-політики-системи)
12. [Acceptance-кейси](#12-acceptance-кейси)
13. [Гарантії та інваріанти](#13-гарантії-та-інваріанти)

---

## 1. Терміни та визначення

### 1.1 Основні поняття

| Термін | Визначення |
|--------|-----------|
| **Slot** | Індекс механізму в масиві DB (0..255). Єдиний ідентифікатор механізму в обміні SCADA ↔ PLC. |
| **Механізм** | Типова сутність (редлер/норія/засувка/вентилятор), реалізована як пасивний FB/FC. |
| **HAL** | Hardware Abstraction Layer - шар нормалізації фізичних сигналів. |
| **Owner** | Поточний власник механізму (NONE/SCADA/ROUTE), має ексклюзивне право на команди. |
| **Арбітр** | Централізована функція (FC_ArbiterMech) для контролю доступу до механізмів. |
| **Маршрут** | Послідовність кроків керування механізмами, виконується FSM у PLC. |
| **FSM** | Finite State Machine - скінченний автомат станів. |

### 1.2 Діючі особи

| Роль | Відповідальність |
|------|------------------|
| **SCADA** | Формує маршрути, ручні команди, відображає стан, журналює події. |
| **PLC** | Виконує механізми, арбітраж, маршрути (FSM), safety, діагностику. |
| **Оператор** | Керує через SCADA UI, підтверджує критичні дії. |

### 1.3 Режими керування

```
┌─────────────────┬──────────────────────────────────────────────┐
│ Режим           │ Опис                                         │
├─────────────────┼──────────────────────────────────────────────┤
│ AUTO            │ PLC керує (SCADA/Route), LocalManual = FALSE │
│ LOCAL MANUAL    │ Ручне керування на місці, PLC не керує       │
│ DISABLED        │ Заборонено Enable_OK = FALSE                 │
│ FAULT           │ Аварійний стан, команди ігноруються          │
└─────────────────┴──────────────────────────────────────────────┘
```

---

## 2. Архітектура системи

### 2.1 Чотирирівнева архітектура (незмінна основа)

```
┌─────────────────────────────────────────────────────────────┐
│ L3: Control Intelligence                                    │
│ ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐   │
│ │ Route FSM       │  │ Manual Ctrl  │  │ Safety Logic   │   │
│ │ (12 паралельних)│  │ Handler      │  │ (Global)       │   │
│ └────────┬────────┘  └──────┬───────┘  └────────────────┘   │
│          │                  │                               │
│          └───────────┬──────┘                               │
│                      ▼                                      │
│              ┌──────────────┐                               │
│              │  FC_Arbiter  │ ← єдине джерело команд        │
│              │  Mech        │                               │
│              └──────────────┘                               │
├─────────────────────────────────────────────────────────────┤
│ L2: Device Runner                                           │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ FC_DeviceRunner: tick всіх механізмів (за типами)        ││
│ └──────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│ L1: Mechanism Layer (пасивні механізми)                     │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│ │FC_Redler │ │FC_Noria  │ │FC_Gate2P │ │FC_Fan    │         │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
├─────────────────────────────────────────────────────────────┤
│ L0: HAL (Hardware Abstraction Layer)                        │
│ ┌──────────────────┐  ┌──────────────────┐                  │
│ │ FC_HAL_Read      │  │ FC_HAL_Write     │                  │
│ │ (Cycle Start)    │  │ (Cycle End)      │                  │
│ └──────────────────┘  └──────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Потік виконання PLC циклу

```
OB1 Cycle (10-20 мс):
  1. FC_HAL_Read()                    // Читання входів
  2. FC_ManualMechCmdHandler()        // Обробка ручних команд (SCADA manual)
  3. FC_RoutesSupervisor()            // Виконання маршрутів FSM
  4. FC_DeviceRunner()                // Виконання механізмів
  5. FC_HAL_Write()                   // Запис виходів

Примітка: Manual та Routes використовують спільний арбітр (FC_ArbiterMech)
```

### 2.3 Slot-based addressing

```
Slot Range    │ Device Type        │ Max Count
──────────────┼────────────────────┼──────────
0..49         │ Redlers            │ 50
50..99        │ Norias             │ 50
100..149      │ Gates              │ 50
150..199      │ Fans               │ 50
200..255      │ Reserved           │ 56
──────────────┴────────────────────┴──────────
Total: 256 slots
```

**Mapping:**
```scl
Mechs[slot].DeviceType  // TYPE_REDLER / TYPE_NORIA / ...
Mechs[slot].TypedIndex  // індекс у типізованому масиві
```

---

## 3. Контракт механізму

### 3.1 Мінімальний інтерфейс (UDT_BaseMechanism)

```scl
TYPE "UDT_BaseMechanism"
STRUCT
    // === Мапінг слоту ===
    DeviceType : USINT;    // TYPE_REDLER / TYPE_NORIA / ...
    TypedIndex : UINT;     // індекс у DB_Mechs.<Type>[TypedIndex]
    
    // === Дозволи / режими ===
    Enable_OK    : BOOL;   // дозвіл на роботу (пермітив)
    LocalManual  : BOOL;   // локальне ручне керування
    
    // === Команди (від арбітра) ===
    Cmd          : USINT;  // CMD_START / CMD_STOP / CMD_RESET
    CmdParam1    : INT;    // параметр команди
    Force_Code   : INT;    // форсування захистів (бітова маска)
    
    // === Власник (арбітраж) ===
    OwnerCur     : USINT;  // OWNER_NONE / OWNER_SCADA / OWNER_ROUTE
    OwnerCurId   : UINT;   // ідентифікатор власника (RouteId)
    
    // === Діагностика ===
    LastCmd      : USINT;  // остання команда (заповнює механізм)
    
    // === Стан та аварії ===
    Status       : UINT;   // STS_IDLE / STS_RUNNING / STS_FAULT / ...
    FLTCode      : UINT;   // код помилки (0 = відсутня)
END_STRUCT;
END_TYPE
```

### 3.2 Правила механізму

**Механізм (FC_Redler/FC_Noria/...) ЗОБОВ'ЯЗАНИЙ:**

1. ✅ Заповнювати `Status` та `FLTCode`
2. ✅ Реагувати на `Cmd` / `CmdParam1` / `Force_Code`
3. ✅ Враховувати `Enable_OK` / `LocalManual`
4. ✅ Фіксувати `LastCmd` при зміні команди
5. ❌ **НЕ ПИСАТИ** `Cmd` напряму (тільки через арбітр)
6. ❌ **НЕ ПИСАТИ** `OwnerCur` / `OwnerCurId` (тільки арбітр або fault cleanup)

**Механізм НЕ ВІДПОВІДАЄ за:**
- ❌ Арбітраж доступу (робить FC_ArbiterMech)
- ❌ Виклик інших механізмів (робить FC_DeviceRunner)
- ❌ Маршрути (робить Route FSM)

---

## 4. Команди та стани

### 4.1 Команди (DB_Const.CMD_*)

```scl
CMD_NONE  : USINT := 0;   // немає команди
CMD_START : USINT := 1;   // запустити механізм
CMD_STOP  : USINT := 2;   // зупинити механізм
CMD_RESET : USINT := 3;   // скинути аварію
```

**Важливо:** Команда - **рівнева** (не імпульсна). Механізм не "гасить" команду після виконання.

### 4.2 Стани (DB_Const.STS_*)

```scl
STS_IDLE     : UINT := 0;    // зупинено, готовий
STS_STARTING : UINT := 1;    // запускається
STS_RUNNING  : UINT := 2;    // працює
STS_STOPPING : UINT := 3;    // зупиняється
STS_FAULT    : UINT := 4;    // аварія
STS_DISABLED : UINT := 10;   // заборонено (Enable_OK=0)
STS_LOCAL    : UINT := 11;   // локальне ручне керування
```

### 4.3 Коди аварій (DB_Const.FLT_*)

```scl
FLT_NONE      : UINT := 0;    // немає аварії
FLT_OVERFLOW  : UINT := 10;   // переповнення
FLT_BREAKER   : UINT := 11;   // автомат захисту
FLT_NO_RUNFB  : UINT := 12;   // немає feedback (таймаут)
FLT_INTERLOCK : UINT := 13;   // блокування інтерлоком
```

### 4.4 FSM типового механізму

```
         CMD_START
IDLE ──────────────► STARTING ──► RUNNING
 ▲                      │            │
 │                      │ timeout    │ CMD_STOP
 │                      ▼            ▼
 └──────────────────── FAULT ◄── STOPPING
         CMD_RESET
         
Блокуючі стани (не виходять самі):
- DISABLED (Enable_OK=0)
- LOCAL (LocalManual=1)
- FAULT (до CMD_RESET)
```

---

## 5. Арбітраж та ownership

### 5.1 Принцип арбітражу

**Єдине правило:**
> Будь-яка команда до механізму проходить через `FC_ArbiterMech`.
> Прямий запис `Cmd` - **порушення контракту**.

**Централізація:**
```
SCADA manual ──┐
               ├──► FC_ArbiterMech ──► Mechs[slot].Cmd
Route FSM   ───┘
```

### 5.2 Owner states

```scl
OWNER_NONE  : USINT := 0;   // вільний
OWNER_SCADA : USINT := 1;   // ручне керування SCADA
OWNER_ROUTE : USINT := 2;   // маршрут (OwnerCurId = RouteId)
```

### 5.3 Правила доступу (FC_ArbiterMech)

**Перевірки (в порядку пріоритету):**

```
1. LocalManualGlobal = TRUE
   └─► allowExec = FALSE (PLC не керує взагалі)

2. M.LocalManual = TRUE
   └─► allowExec = FALSE (локальний режим)

3. M.DeviceType = TYPE_NONE OR M.TypedIndex = 0xFFFF
   └─► allowExec = FALSE (слот не замаплений)

4. M.OwnerCur = OWNER_NONE AND OwnerReq != OWNER_NONE
   └─► M.OwnerCur := OwnerReq (захват owner)
   
5. M.OwnerCur != OwnerReq OR M.OwnerCurId != OwnerReqId
   └─► allowExec = FALSE (owner не співпадає)

6. ReqCmd = CMD_NONE AND NOT ReleaseOwner
   └─► allowExec = FALSE (порожній запит)

7. Усі перевірки пройдено
   └─► M.Cmd := ReqCmd (запис команди)
```

### 5.4 Звільнення Owner

#### Автоматичне звільнення:

```
✅ DONE маршруту (фінальний стан)
✅ REJECTED маршруту (фінальний стан)
✅ ABORTED маршруту (після STOPPING → ABORTED)
```

#### Fault НЕ звільняє owner автоматично:

```
❌ Manual control: owner = OWNER_SCADA (залишається)
❌ Route: owner = OWNER_ROUTE (FSM зробить cleanup через STOPPING)

Обґрунтування:
- Owner має відповідальність за відновлення (atomic responsibility)
- Трейсабільність (видно хто запустив)
- Захист від race conditions
```

#### Явне звільнення (ReleaseOwner):

```scl
FC_ArbiterMech(
    OwnerReq     := OWNER_SCADA,
    ReleaseOwner := TRUE,
    M            := Mechs[slot]
);

// Перевірка:
IF (M.OwnerCur = OwnerReq) AND (M.OwnerCurId = OwnerReqId) THEN
    M.OwnerCur   := OWNER_NONE;
    M.OwnerCurId := 0;
END_IF;
```

**SCADA може звільнити owner тільки якщо `OwnerCur = OWNER_SCADA`.**

### 5.5 Lock-only режим

```scl
FC_ArbiterMech(
    LockOnly := TRUE,  // тільки перевірка та захват owner
    M        := Mechs[slot]
);

// Використання:
// - Route FSM: atomic lock всіх механізмів перед стартом
// - Перевірка доступності без виконання команди
```

---

## 6. Маршрути

### 6.1 Структура маршруту

**Маршрут складається з:**
- `RouteId` (1..12) - ідентифікатор маршруту
- `StepCount` (0..64) - кількість кроків
- `Steps[]` - масив кроків

**Крок маршруту:**
```scl
TYPE "UDT_RouteStep"
STRUCT
    RS_Slot      : UINT;   // slot механізму
    RS_Action    : USINT;  // RS_ACT_START / RS_ACT_STOP
    RS_Wait      : USINT;  // RS_WAIT_RUNNING / RS_WAIT_STOPPED
    RS_TimeoutMs : DINT;   // таймаут кроку (0 = без таймауту)
END_STRUCT;
```

### 6.2 Route FSM (9 станів)

```
                    E_START
IDLE ───────────────────────► VALIDATING
                                  │
                                  │ pre-checks OK
                                  ▼
                              LOCKING (atomic)
                                  │
                                  │ lock OK
                                  ▼
                              STARTING
                                  │
                                  │ E_ALL_STARTED
                                  ▼
                              RUNNING ◄─────┐
                                  │         │
                    E_STOP_OP     │         │ step → step
                    E_LOCAL       │         │
                    E_FAULT       │         └─────
                                  │
                                  ▼
                              STOPPING
                                  │
                                  │ E_ALL_STOPPED
                                  ▼
           ┌──────────────────────┴──────────────────────┐
           ▼                      ▼                       ▼
        DONE                  REJECTED                ABORTED
     (фінальний)            (фінальний)             (фінальний)
```

### 6.3 Validating phase (pre-checks)

**Перевірки перед стартом:**

```
1. StepCount > 0
   └─► інакше REJECTED_BY_CONTRACT

2. Для кожного кроку:
   a) Slot існує (DeviceType != TYPE_NONE, TypedIndex != 0xFFFF)
      └─► інакше REJECTED_BY_CONTRACT
   
   b) Action валідна (RS_ACT_START / RS_ACT_STOP)
      └─► інакше REJECTED_BY_CONTRACT
   
   c) Wait валідна (RS_WAIT_RUNNING / RS_WAIT_STOPPED)
      └─► інакше REJECTED_BY_CONTRACT
   
   d) OwnerCur = OWNER_NONE
      └─► інакше REJECTED_BY_OWNER
   
   e) Enable_OK = TRUE
      └─► інакше REJECTED_NOT_READY
   
   f) LocalManual = FALSE
      └─► інакше REJECTED_NOT_READY
   
   g) FLTCode = 0
      └─► інакше REJECTED_NOT_READY

3. GlobalSafetyStop = FALSE
   └─► інакше REJECTED_BY_SAFETY

4. Дублікат START (той самий RouteId активний)
   └─► інакше REJECTED_DUPLICATE_START
```

**Важливо:** У VALIDATING **НЕ робиться side-effects** (немає lock, немає команд).

### 6.4 Locking phase (atomic)

```scl
// Спроба захватити owner всіх механізмів атомарно
lockOkAll := TRUE;

FOR i := 0 TO stepCnt - 1 DO
    lockOkOne := FC_ArbiterMech(
        OwnerReq := OWNER_ROUTE,
        OwnerReqId := RouteId,
        LockOnly := TRUE,  // без команд
        M := Mechs[slot]
    );
    
    IF NOT lockOkOne THEN
        lockOkAll := FALSE;
    END_IF;
END_FOR;

IF NOT lockOkAll THEN
    // Відкат (release всіх частково захвачених)
    FOR i := 0 TO stepCnt - 1 DO
        FC_ArbiterMech(ReleaseOwner := TRUE, ...);
    END_FOR;
    
    → REJECTED_BY_OWNER
ELSE
    → STARTING
END_IF;
```

**Гарантія:** або всі механізми locked, або нічого (atomic).

### 6.5 Виконання кроків (RUNNING)

```scl
stepIdx := Fsm.RF_ActiveStep;

IF stepIdx >= stepCnt THEN
    // Усі кроки виконано
    → DONE
END_IF;

slot := Cmd.RC_Steps[stepIdx].RS_Slot;

// Виконати команду через арбітр
IF Steps[stepIdx].RS_Action = RS_ACT_START THEN
    cmdOk := FC_ArbiterMech(ReqCmd := CMD_START, ...);
ELSE
    cmdOk := FC_ArbiterMech(ReqCmd := CMD_STOP, ...);
END_IF;

// Чекати виконання
IF Steps[stepIdx].RS_Wait = RS_WAIT_RUNNING THEN
    IF Mechs[slot].Status = STS_RUNNING THEN
        Fsm.RF_ActiveStep += 1;  // наступний крок
    END_IF;
ELSE
    IF Mechs[slot].Status = STS_IDLE THEN
        Fsm.RF_ActiveStep += 1;
    END_IF;
END_IF;
```

### 6.6 Abort scenarios

```
E_STOP_OP (SCADA Stop)
├─► STOPPING → allStopped → ABORTED_BY_OPERATOR

E_LOCAL_MANUAL (LocalManualGlobal=1 або M.LocalManual=1)
├─► STOPPING → allStopped → ABORTED_BY_LOCAL

E_FAULT (anyFault=TRUE на будь-якому slot)
├─► STOPPING → allStopped → ABORTED_BY_FAULT

E_SAFETY_STOP (GlobalSafetyStop=1)
├─► негайний STOP → ABORTED_BY_SAFETY (без STOPPING)
```

### 6.7 Інваріанти маршрутів

```
✅ Один slot не може належати двом активним маршрутам
✅ Якщо OwnerCur = ROUTE → SCADA manual заборонено
✅ Дублікат START → REJECTED_DUPLICATE_START
✅ START при GlobalSafetyStop=1 → REJECTED_BY_SAFETY
✅ Після ABORTED/DONE/REJECTED → owner звільняється
```

---

## 7. Manual Control (ручне керування зі SCADA)

### 8.1 Призначення

**Manual Control** - режим прямого керування окремими механізмами оператором через SCADA UI без створення маршрутів.

**Коли використовується:**
```
✅ Налагодження механізмів
✅ Обслуговування обладнання
✅ Тестування після ремонту
✅ Аварійне керування (якщо маршрути недоступні)
```

**Обмеження:**
```
❌ Не можна керувати механізмом у маршруті (OwnerCur = ROUTE)
❌ Не працює при LocalManual = TRUE
❌ Не працює при Enable_OK = FALSE
❌ Не працює при GlobalSafetyStop = TRUE
```

### 8.2 Протокол обміну (commit-based)

**SCADA → PLC:**
```scl
DB_ScadaToPlc_ManualMechCmd.CmdBySlot[slot]
  Commit       : UDINT   // лічильник змін (SCADA інкрементує)
  Cmd          : USINT   // CMD_START / CMD_STOP / CMD_RESET
  Param1       : INT     // параметр команди
  Force_Code   : INT     // форсування захистів
  ReleaseOwner : BOOL    // звільнити owner після команди
```

**PLC → SCADA:**
```scl
DB_PlcToScada_ManualMechStatus.StatusBySlot[slot]
  ManualAllowed : BOOL   // TRUE = можна керувати
  AckCommit     : UDINT  // підтверджений commit
  AckOk         : BOOL   // TRUE = команда прийнята
  RejectCode    : USINT  // причина відмови (0 = OK)
  CurrentOwner  : USINT  // поточний owner (діагностика)
  CurrentStatus : UINT   // поточний статус (діагностика)
```

### 8.3 Workflow SCADA manual

```
┌─────────────────────────────────────────────────────────────┐
│ Крок 1: SCADA перевіряє ManualAllowed                       │
├─────────────────────────────────────────────────────────────┤
│ IF StatusBySlot[slot].ManualAllowed = TRUE THEN             │
│     → кнопки START/STOP активні                             │
│ ELSE                                                         │
│     → кнопки заблоковані (показати причину)                 │
│ END_IF                                                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Крок 2: Оператор натискає START                             │
├─────────────────────────────────────────────────────────────┤
│ CmdBySlot[slot].Cmd := CMD_START                            │
│ CmdBySlot[slot].Commit := Commit + 1  ← ATOMIC INCREMENT    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Крок 3: PLC обробляє (FC_ManualMechCmdHandler)              │
├─────────────────────────────────────────────────────────────┤
│ IF Commit != LastCommitSeen[slot] THEN                      │
│     LastCommitSeen[slot] := Commit                          │
│     → Валідація (ManualAllowed)                             │
│     → FC_ArbiterMech(OwnerReq := OWNER_SCADA, Cmd := START) │
│     → StatusBySlot[slot].AckCommit := Commit                │
│     → StatusBySlot[slot].AckOk := TRUE/FALSE                │
│ END_IF                                                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Крок 4: SCADA бачить підтвердження                          │
├─────────────────────────────────────────────────────────────┤
│ WHILE StatusBySlot[slot].AckCommit != MyCommit DO           │
│     WAIT (polling 100-500 мс)                               │
│ END_WHILE                                                    │
│                                                              │
│ IF StatusBySlot[slot].AckOk = TRUE THEN                     │
│     → "Команда виконана" ✅                                 │
│ ELSE                                                         │
│     → "Помилка: " + RejectCode ❌                           │
│ END_IF                                                       │
└─────────────────────────────────────────────────────────────┘
```

### 8.4 Reject codes (причини відмови)

```scl
MAN_REJ_OK            : USINT := 0;  // команда прийнята
MAN_REJ_SLOT_UNMAPPED : USINT := 1;  // слот не існує
MAN_REJ_LOCAL_MANUAL  : USINT := 2;  // локальний режим
MAN_REJ_NOT_ENABLED   : USINT := 3;  // Enable_OK = FALSE
MAN_REJ_OWNER_BUSY    : USINT := 4;  // owner зайнято (route/інший)
MAN_REJ_CMD_INVALID   : USINT := 5;  // команда некоректна
MAN_REJ_ARBITER_FAIL  : USINT := 6;  // арбітр відхилив
```

### 8.5 ManualAllowed calculation

```scl
// FC_ManualMechCmdHandler розраховує кожен цикл:
allowed := (Mechs[slot].DeviceType != TYPE_NONE)           // замаплений
           AND (Mechs[slot].TypedIndex != 0xFFFF)          // замаплений
           AND (Mechs[slot].OwnerCur = OWNER_NONE)         // вільний
           AND (NOT LocalManualGlobal)                     // не глобальний ручний
           AND (NOT Mechs[slot].LocalManual)               // не локальний ручний
           AND (Mechs[slot].Enable_OK);                    // дозволено

StatusBySlot[slot].ManualAllowed := allowed;

// SCADA UI використовує для блокування кнопок
```


```

### 8.7 Приклад: SCADA START → RUNNING

```
T=0ms     SCADA UI
          ├─ Оператор: натискає START на Redler_1
          └─ CmdBySlot[0].Cmd := CMD_START
              CmdBySlot[0].Commit := 123 (було 122)

T=10ms    PLC Cycle N (FC_ManualMechCmdHandler)
          ├─ Detect: Commit (123) != LastCommitSeen (122)
          ├─ Validate: ManualAllowed = TRUE ✅
          ├─ FC_ArbiterMech:
          │  ├─ OwnerCur = NONE → захват OWNER_SCADA
          │  └─ Mechs[0].Cmd := CMD_START
          ├─ StatusBySlot[0].AckCommit := 123
          └─ StatusBySlot[0].AckOk := TRUE

T=20ms    PLC Cycle N+1 (FC_DeviceRunner → FC_Redler)
          ├─ B.Cmd = CMD_START
          ├─ B.Status: IDLE → STARTING
          ├─ R.StartMs := TIME_TCK()
          └─ R.DO_Run := TRUE

T=30ms    FC_HAL_Write
          └─ "Redler_1_DO_Run" := TRUE → %Q0.0 = TRUE
              → Контактор замикається → мотор стартує

T=500ms   PLC Cycle N+50 (FC_Redler)
          ├─ R.DI_Speed_OK = TRUE (тахо-датчик)
          └─ B.Status: STARTING → RUNNING ✅

T=510ms   SCADA poll
          ├─ StatusBySlot[0].AckCommit = 123 (наш commit)
          ├─ StatusBySlot[0].CurrentStatus = STS_RUNNING
          └─ UI: "Redler_1: RUNNING" ✅
```

### 8.8 ReleaseOwner механізм

**Сценарій:** SCADA хоче звільнити owner після виконання команди.

```python
# SCADA код
def manual_start_and_release(slot):
    # 1. START + ReleaseOwner одночасно (НЕ ПРАЦЮЄ в поточній версії!)
    # Причина: ReleaseOwner перевіряється ПЕРЕД командою і робить CONTINUE
    
    # 2. Правильний спосіб (2 запити):
    send_command(slot, CMD_START)
    wait_for_ack(slot)
    
    send_release_owner(slot)  # окремий запит
    wait_for_ack(slot)
```

```scl
// FC_ManualMechCmdHandler (поточна логіка)
// 5️⃣ ReleaseOwner (ПЕРЕД командою)
IF (rej = MAN_REJ_OK) AND CmdBySlot[i].ReleaseOwner THEN
    ok := FC_ArbiterMech(ReleaseOwner := TRUE, ...);
    StatusBySlot[i].AckCommit := commitIn;
    CONTINUE;  // ← виходимо, команда НЕ виконується!
END_IF;

// 7️⃣ Виконання команди (не досягається якщо ReleaseOwner=TRUE)
IF rej = MAN_REJ_OK THEN
    ok := FC_ArbiterMech(ReqCmd := Cmd, ...);
END_IF;
```

**Рекомендація для майбутньої версії:** дозволити ReleaseOwner + Cmd одночасно (виконувати команду, потім release).

### 8.9 Fault handling в manual mode

**Сценарій:** механізм запущений через SCADA manual → fault.

```
T=0     SCADA: START slot 0
        → OwnerCur = OWNER_SCADA
        → Status = RUNNING

T=500   Fault: DI_Breaker_OK = FALSE
        → Status = STS_FAULT
        → FLTCode = FLT_BREAKER
        → OwnerCur = OWNER_SCADA  ← ЗАЛИШАЄТЬСЯ! (згідно з P2)
        → DO_Run = FALSE (мотор зупинився)

T=510   SCADA poll:
        → CurrentStatus = STS_FAULT
        → CurrentOwner = OWNER_SCADA
        → ManualAllowed = FALSE (FLTCode != 0)
        → UI: показати аварію + кнопка RESET активна

T=600   Оператор: натискає RESET
        SCADA: send_command(slot=0, CMD_RESET)

T=610   PLC: FC_ArbiterMech
        → okOwner = TRUE (OwnerCur = SCADA)
        → Mechs[0].Cmd := CMD_RESET ✅

T=620   PLC: FC_Redler
        → B.Cmd = CMD_RESET
        → Status := STS_IDLE
        → FLTCode := FLT_NONE
        → OwnerCur = OWNER_SCADA (ЩЕ залишається!)

T=630   SCADA: (опційно) send_release_owner(slot=0)
        → OwnerCur = OWNER_NONE
```

**Важливо:** Owner залишається після fault, що дозволяє SCADA робити RESET без конфліктів.

### 8.10 Взаємодія Manual ↔ Routes

**Правило:** Manual та Routes взаємовиключні (через owner).

```
Ситуація 1: Route активний → Manual заблокований
├─ Route 1 запустив slot 0 (OwnerCur = OWNER_ROUTE)
├─ SCADA: ManualAllowed[0] = FALSE
└─ UI: кнопки START/STOP заблоковані

Ситуація 2: Manual активний → Route не може захватити
├─ SCADA manual запустив slot 0 (OwnerCur = OWNER_SCADA)
├─ Route намагається START slot 0 (VALIDATING phase)
├─ Перевірка: OwnerCur != OWNER_NONE
└─ Route → REJECTED_BY_OWNER

Ситуація 3: Manual RESET не впливає на Route ownership
├─ Route 1 у FAULT (OwnerCur = OWNER_ROUTE)
├─ SCADA manual RESET → FC_ArbiterMech
├─ okOwner = FALSE (OwnerCur != OWNER_SCADA)
└─ Команда ігнорується

Рішення для Ситуації 3:
├─ Route FSM сам робить cleanup (STOPPING → ABORTED)
└─ Потім SCADA може manual RESET
```

### 8.11 Performance metrics

```
Параметр                  │ Значення
──────────────────────────┼─────────────────────
Слотів на обробку         │ 256
Слотів за цикл            │ 32 (налаштовується)
Циклів для повного scan   │ 8
Час циклу PLC             │ 10-20 мс
Max затримка реакції      │ 80-160 мс
Розмір команди (SCADA→PLC)│ 16 байт
Розмір статусу (PLC→SCADA)│ 12 байт
RAM для 256 слотів        │ ~7 KB
──────────────────────────┴─────────────────────
```

### 8.12 SCADA UI рекомендації

**Відображення стану механізму:**
```
┌────────────────────────────────────┐
│ Редлер_1 (Slot 0)                  │
├────────────────────────────────────┤
│ Статус:  ●RUNNING                  │
│ Власник: Manual (SCADA)            │
│ Аварія:  Немає                     │
│                                    │
│ [START]  [STOP]  [RESET]          │
│  (disabled) (active) (disabled)   │
│                                    │
│ ManualAllowed: ✅                  │
│ LastCmd: START                     │
│ DO_Run: TRUE                       │
└────────────────────────────────────┘
```

**Блокування UI:**
```python
# SCADA логіка
def update_ui(slot):
    status = read_status(slot)
    
    # Базове блокування
    if not status.ManualAllowed:
        disable_all_buttons()
        show_reason(status.CurrentOwner, status.CurrentStatus)
        return
    
    # Стан-залежне блокування
    if status.CurrentStatus == STS_IDLE:
        enable_button(START)
        disable_button(STOP)
        disable_button(RESET)
    
    elif status.CurrentStatus == STS_RUNNING:
        disable_button(START)
        enable_button(STOP)
        disable_button(RESET)
    
    elif status.CurrentStatus == STS_FAULT:
        disable_button(START)
        disable_button(STOP)
        enable_button(RESET)
```

**Timeout обробка:**
```python
# SCADA не чекає нескінченно
def send_command_with_timeout(slot, cmd, timeout_sec=5):
    my_commit = increment_commit(slot, cmd)
    
    start_time = time.now()
    while True:
        status = read_status(slot)
        
        if status.AckCommit == my_commit:
            if status.AckOk:
                return SUCCESS
            else:
                return REJECTED(status.RejectCode)
        
        if (time.now() - start_time) > timeout_sec:
            return TIMEOUT
        
        sleep(0.1)  # polling interval
```

---

## 8. Safety та інтерлоки

### 8.1 Global Safety Stop

**Джерела:**
```
GlobalSafetyStop = HW_ESTOP OR SCADA_SafetyStop

HW_ESTOP        - апаратна кнопка аварійного зупину
SCADA_SafetyStop - кнопка Safety Stop у SCADA UI
```

**Дія:**
```
1. Негайний STOP усіх виходів (DO_Run = FALSE)
2. Усі маршрути → ABORTED_BY_SAFETY
3. Owner звільняється одразу (без STOPPING phase)
4. START заборонено до зняття GlobalSafetyStop
```

### 8.2 Local Manual (глобальний)

```scl
LocalManualGlobal : BOOL  // глобальний сигнал "Ручний режим"

IF LocalManualGlobal = TRUE THEN
    // PLC не видає команд
    // Маршрути → ABORTED_BY_LOCAL (через STOPPING)
    // Діагностика продовжується
END_IF;
```

### 8.3 Local Manual (per-device)

```scl
Mechs[slot].LocalManual : BOOL  // локальний перемикач

IF Mechs[slot].LocalManual = TRUE THEN
    // Механізм → STS_LOCAL
    // Owner скидається
    // PLC не керує цим механізмом
END_IF;
```

### 8.4 Enable (дозвіл на роботу)

```scl
Mechs[slot].Enable_OK : BOOL  // пермітив (від safety PLC)

IF Mechs[slot].Enable_OK = FALSE THEN
    // Механізм → STS_DISABLED
    // Owner скидається
    // START неможливий
END_IF;
```

### 8.5 Пріоритети

```
1. GlobalSafetyStop (найвищий)
   └─► негайний STOP, ABORTED_BY_SAFETY

2. LocalManualGlobal
   └─► PLC не керує, ABORTED_BY_LOCAL

3. Enable_OK = FALSE
   └─► STS_DISABLED, owner скидається

4. M.LocalManual = TRUE
   └─► STS_LOCAL, owner скидається

5. FLTCode != 0
   └─► STS_FAULT, owner залишається

6. Нормальна робота
   └─► AUTO режим
```

---

## 9. Fault handling

### 8.1 Типи аварій

```
Місцеві аварії (детектуються механізмом):
├─ FLT_BREAKER   - автомат захисту
├─ FLT_OVERFLOW  - переповнення
├─ FLT_NO_RUNFB  - немає feedback (таймаут запуску/втрата швидкості)
└─ FLT_INTERLOCK - блокування інтерлоком

Глобальні аварії (детектуються safety):
└─ GlobalSafetyStop - аварійний зупин
```

### 8.2 Поведінка механізму при fault

```scl
// FC_Redler (приклад)
IF (NOT R.DI_Breaker_OK) AND (NOT forceBreaker) THEN
    B.FLTCode := FLT_BREAKER;
    B.Status  := STS_FAULT;
    
    // ⚠️ ВАЖЛИВО: Owner НЕ звільняється!
    // (згідно з контрактом v2.1.0 #8.3)
    
    isFault := TRUE;
END_IF;

// Вихід вимикається автоматично
IF (B.Status = STS_STARTING) OR (B.Status = STS_RUNNING) THEN
    R.DO_Run := TRUE;
ELSE
    R.DO_Run := FALSE;  // ← FAULT → DO_Run = FALSE
END_IF;
```

### 8.3 Owner при fault (ключове правило)

**Manual control:**
```
Fault detected
└─► Status = STS_FAULT
    FLTCode = FLT_*
    OwnerCur = OWNER_SCADA  ← ЗАЛИШАЄТЬСЯ!
    DO_Run = FALSE

SCADA може:
1. RESET (бо owner = SCADA)
   └─► Status = STS_IDLE, FLTCode = FLT_NONE
   
2. ReleaseOwner (опційно)
   └─► OwnerCur = OWNER_NONE
```

**Route:**
```
Fault detected на будь-якому slot
└─► anyFault = TRUE
    
Route FSM:
├─► State = STOPPING
│   ├─ Контрольований STOP всіх механізмів
│   └─ Чекає E_ALL_STOPPED
│
├─► State = ABORTED
│   ├─ ResultCode = ROUTE_ABRT_BY_FAULT
│   └─► Owner звільняється для ВСІХ механізмів
│
└─► Owner залишався під час STOPPING (координація cleanup)
```

**Обґрунтування:**
```
✅ Atomic responsibility (хто запустив → відповідає за recovery)
✅ Трейсабільність (owner видно в статусі)
✅ Захист від race (slot locked до cleanup)
✅ Route FSM керує cleanup через STOPPING phase
```

### 8.4 Recovery patterns

#### Pattern 1: Manual control fault recovery

```python
# SCADA код
def handle_manual_fault(slot):
    status = read_status(slot)
    
    if status.CurrentStatus == STS_FAULT:
        # 1. Журналювання
        log_fault(
            slot=slot,
            fault_code=status.FLTCode,
            owner=status.CurrentOwner
        )
        
        # 2. Чекати підтвердження оператора
        if operator_confirm_reset():
            # 3. RESET (owner залишається SCADA)
            send_command(slot, CMD_RESET)
            wait_for_status(slot, STS_IDLE)
            
            # 4. (Опційно) Звільнити owner
            if not continue_operation:
                send_release_owner(slot)
```

#### Pattern 2: Route fault recovery

```
Route FSM автоматично:

1. Fault detected → anyFault = TRUE
2. RUNNING → STOPPING
3. Контрольований STOP (зворотній порядок)
4. E_ALL_STOPPED → ABORTED
5. Release owner всіх механізмів
6. ResultCode = ROUTE_ABRT_BY_FAULT

SCADA:
- Бачить State = ABORTED
- Бачить ResultCode = ROUTE_ABRT_BY_FAULT
- Журналює подію
- Чекає підтвердження оператора на повторний START
```

### 8.5 Форсування захистів (Force_Code)

```scl
// Бітова маска для обходу захистів (під час обслуговування)
Force_Code : INT

BIT0 (1) - подавити FLT_OVERFLOW
BIT1 (2) - подавити FLT_BREAKER
BIT2 (4) - подавити FLT_NO_RUNFB (таймаути)

// Приклад
IF (NOT R.DI_Breaker_OK) AND (NOT forceBreaker) THEN
    B.FLTCode := FLT_BREAKER;
    B.Status  := STS_FAULT;
END_IF;

forceBreaker := (B.Force_Code AND 2) <> 0;
```

**Використання:** тільки для налагодження та обслуговування!

---

## 10. Розподіл відповідальності

### 13.1 SCADA відповідальність

```
Процеси (що/навіщо/коли):
├─ Формувати маршрути (послідовність, параметри)
├─ Ручне керування (manual commands)
├─ Підтвердження критичних дій (safety stop, reset)
├─ Відображення стану (UI)
├─ Журналювання подій
└─ Звіти та аналітика

НЕ відповідає за:
❌ Детерміноване виконання (робить PLC FSM)
❌ Арбітраж (робить FC_ArbiterMech)
❌ Safety (робить safety logic)
❌ Прямий запис I/O (робить HAL)
```

### 13.2 PLC відповідальність

```
Виконання (як/з якими гарантіями):
├─ Детермінований FSM (механізми, маршрути)
├─ Арбітраж доступу (owner management)
├─ Safety logic (GlobalSafetyStop, Enable, LocalManual)
├─ Діагностика (FLTCode, Status, таймінги)
└─ HAL (нормалізація I/O)

НЕ відповідає за:
❌ Процесну логіку (робить SCADA)
❌ Оптимізацію технології (робить SCADA)
❌ UI/UX (робить SCADA)
❌ Звіти (робить SCADA)
```

### 13.3 "Граничні закони"

```
PLC НЕ містить:
❌ "Розумної" логіки (if day_of_week = Monday then...)
❌ Оптимізацій (мінімізація енергії, час виконання)
❌ Бізнес-правил (якщо клієнт VIP, то...)

PLC містить ТІЛЬКИ:
✅ Правила "можна/не можна" (safety, owner, enable)
✅ FSM (детермінований автомат станів)
✅ Таймінги та timeout (для safety)
✅ Діагностику (fault codes, status)
```

**Принцип:** PLC - це "тупий виконавець", який гарантує safety та детермінізм. SCADA - "розумний керівник", який знає про процес.

---

## 11. Політики системи

### 13.1 Конфігуровані політики (DB_Const)

```scl
// P1: LocalManualGlobal behavior
POLICY_LOCAL_MANUAL_MODE : USINT := 1;
// 0 = PAUSE (not implemented)
// 1 = ABORT (рекомендовано, реалізовано)

// Майбутні політики (для розширення):
// POLICY_OWNER_TIMEOUT_SEC : DINT := 300;  // 5 хвилин
// POLICY_FAULT_AUTO_RESET  : BOOL := FALSE;
```

### 13.2 Фіксовані політики (не конфігуруються)

```
P2: RELEASE_ON_FAULT = FALSE
└─► Owner залишається при fault
    Обґрунтування: atomic responsibility, traceability

P3: Route FSM: БЕЗ PAUSE
└─► Немає станів PAUSE/RESUME
    Обґрунтування: спрощення FSM, уникнення edge cases

P4: Fault = аварія (завжди)
└─► FLTCode != 0 → Status = STS_FAULT
    Немає "некритичних" fault (є warnings, але окремо)

P5: Command = рівнева
└─► Cmd не "гаситься" механізмом після виконання
    SCADA має явно писати CMD_NONE для скидання
```

---

## 12. Acceptance-кейси

### 13.1 AC-01: Перетин маршрутів

```
Дано:
- Route 1 активний (slots: 0, 50, 100)
- SCADA намагається запустити Route 2 (slots: 50, 51, 101)

Очікування:
- Route 2 → VALIDATING
- Перевірка: Mechs[50].OwnerCur != OWNER_NONE
- Route 2 → REJECTED_BY_OWNER
- ResultCode = ROUTE_REJ_BY_OWNER

Гарантія:
✅ Один slot не може належати двом маршрутам одночасно
```

### 13.2 AC-02: SCADA manual у маршруті

```
Дано:
- Route 1 активний (slots: 0, 50, 100)
- Оператор намагається manual START slot 0 через SCADA

Очікування:
- FC_ManualMechCmdHandler
- Перевірка ManualAllowed:
  allowed := (Mechs[0].OwnerCur = OWNER_NONE)  // FALSE!
- ManualAllowed = FALSE
- SCADA бачить "заблоковано"
- Якщо все ж таки send_command → FC_ArbiterMech повертає FALSE

Гарантія:
✅ SCADA не може керувати slot, який належить маршруту
```

### 13.3 AC-03: LocalManualGlobal під час RUNNING

```
Дано:
- Route 1 у стані RUNNING (slots: 0, 50, 100)
- Оператор натискає "Local Manual" на панелі

Очікування:
- LocalManualGlobal := TRUE
- FB_RouteFSM (наступний цикл):
  anyLocal := TRUE
  → Fsm.RF_State = STOPPING
  → Fsm.RF_AbortLatched = ROUTE_ABRT_BY_LOCAL
- Контрольований STOP всіх механізмів
- E_ALL_STOPPED → ABORTED_BY_LOCAL
- Owner звільняється

Гарантія:
✅ LocalManualGlobal зупиняє всі маршрути контрольовано
```

### 13.4 AC-04: Повернення AUTO

```
Дано:
- LocalManualGlobal = TRUE
- Усі маршрути ABORTED_BY_LOCAL
- Оператор повертає LocalManualGlobal = FALSE

Очікування:
- Механізми залишаються у STS_IDLE / STS_STOPPED
- Owner = OWNER_NONE (був звільнений при ABORT)
- SCADA може запустити нові маршрути
- SCADA може manual START

Гарантія:
✅ Система повертається у початковий стан (готова до нових команд)
```

### 13.5 AC-05: Fault → owner залишається

**AC-05a: Manual control fault**

```
Дано:
- SCADA manual START slot 0 (Redler)
- Mechs[0].OwnerCur = OWNER_SCADA
- Mechs[0].Status = STS_RUNNING
- Fault: DI_Breaker_OK = FALSE

Очікування:
- Mechs[0].Status = STS_FAULT
- Mechs[0].FLTCode = FLT_BREAKER
- Mechs[0].OwnerCur = OWNER_SCADA  ← ЗАЛИШАЄТЬСЯ!
- Mechs[0].DO_Run = FALSE (мотор зупинився)

SCADA може:
1. RESET (бо owner = SCADA):
   send_command(slot=0, CMD_RESET)
   → Status = STS_IDLE, FLTCode = FLT_NONE, owner = SCADA

2. ReleaseOwner (опційно):
   send_release_owner(slot=0)
   → OwnerCur = OWNER_NONE

Гарантія:
✅ SCADA, яка запустила, може робити RESET
✅ Інші не можуть втрутитись (owner зайнято)
✅ Трейсабільність (owner видно в статусі)
```

**AC-05b: Route fault**

```
Дано:
- Route 1 RUNNING (slots: 0, 50, 100)
- Fault на slot 0: DI_Breaker_OK = FALSE

Очікування:
- Mechs[0].Status = STS_FAULT, OwnerCur = OWNER_ROUTE
- FB_RouteFSM:
  anyFault = TRUE
  → State = STOPPING
  → Контрольований STOP (reverse order: 100, 50, 0)
  → E_ALL_STOPPED
  → State = ABORTED
  → ResultCode = ROUTE_ABRT_BY_FAULT
  → Release owner всіх slots (0, 50, 100)

Результат:
- Mechs[0,50,100].OwnerCur = OWNER_NONE
- Mechs[0].Status = STS_FAULT (залишається до RESET)
- Route 1 готовий до нового START (після RESET slot 0)

Гарантія:
✅ Route FSM керує cleanup (контрольований STOP)
✅ Owner звільняється після STOPPING phase
✅ Інші маршрути можуть використати slots 50, 100 (після cleanup)
```

---

## 13. Гарантії та інваріанти

### 13.1 Гарантії системи

```
G1: Єдине джерело команд
└─► Всі команди проходять через FC_ArbiterMech

G2: Єдине джерело стану
└─► Status та FLTCode заповнюються тільки механізмом

G3: Owner не може бути захвачений силою
└─► FC_ArbiterMech перевіряє owner перед кожною командою

G4: Механізм у FAULT не приймає START/STOP
└─► Команди ігноруються до CMD_RESET

G5: LocalManual має вищий пріоритет за owner
└─► LocalManual → allowExec = FALSE (навіть якщо owner правильний)

G6: GlobalSafetyStop зупиняє ВСЕ
└─► Негайний STOP, ABORTED_BY_SAFETY, owner звільняється

G7: Route FSM детермінований
└─► Для кожного стану + подія → відома наступна дія

G8: Fault НЕ звільняє owner
└─► Owner залишається для координації recovery
```

### 13.2 Інваріанти

**Перед кожним PLC циклом:**

```
I1: Mechs[slot].OwnerCur ∈ {OWNER_NONE, OWNER_SCADA, OWNER_ROUTE}

I2: IF Mechs[slot].OwnerCur = OWNER_ROUTE THEN
       ∃ RouteId : Fsm[RouteId].State ∈ {STARTING..STOPPING}
       AND Mechs[slot] ∈ Fsm[RouteId].Steps[]

I3: IF Mechs[slot].LocalManual = TRUE THEN
       Mechs[slot].Status = STS_LOCAL
       Mechs[slot].OwnerCur = OWNER_NONE

I4: IF Mechs[slot].Enable_OK = FALSE THEN
       Mechs[slot].Status = STS_DISABLED
       Mechs[slot].OwnerCur = OWNER_NONE

I5: IF Mechs[slot].Status = STS_FAULT THEN
       Mechs[slot].FLTCode != FLT_NONE
       Mechs[slot].OwnerCur ∈ {OWNER_SCADA, OWNER_ROUTE, OWNER_NONE}
       
I6: IF GlobalSafetyStop = TRUE THEN
       ∀ RouteId : Fsm[RouteId].State = ABORTED_BY_SAFETY
       ∀ slot : Mechs[slot].DO_Run = FALSE (HAL forced)

I7: ∀ RouteId : ∀ step ∈ Fsm[RouteId].Steps :
       IF Fsm[RouteId].State ∈ {STARTING..STOPPING} THEN
           Mechs[step.Slot].OwnerCur = OWNER_ROUTE
           Mechs[step.Slot].OwnerCurId = RouteId
```

---

## 📚 Додатки

### Додаток A: DB mapping

```
DB_Const              - константи (CMD_*, STS_*, FLT_*, TYPE_*, OWNER_*)
DB_Const_Routes       - константи маршрутів (ROUTE_STS_*, ROUTE_REJ_*, ...)

DB_Mechs              - механізми
  ├─ Mechs[0..255]    - базова шина (UDT_BaseMechanism)
  ├─ Redler[0..N]     - типізовані редлери
  ├─ Noria[0..N]      - типізовані норії
  ├─ Gate[0..N]       - типізовані засувки
  └─ Fan[0..N]        - типізовані вентилятори

DB_ScadaToPlc_ManualMechCmd     - команди manual (SCADA → PLC)
DB_PlcToScada_ManualMechStatus  - статуси manual (PLC → SCADA)
DB_Plc_ManualMechAux            - внутрішня пам'ять manual handler

DB_ScadaToPlc_RouteCmd          - команди маршрутів (double buffer)
DB_PlcToScada_RouteStatus       - статуси маршрутів
DB_Plc_RouteFsm                 - внутрішня пам'ять FSM
```

### Додаток B: Версії контракту

```
v1.0.0 - Початкова версія (proof of concept)
v1.1.0 - Додано manual control
v1.2.0 - Додано Route FSM (basic)
v1.3.0 - Додано double buffer для маршрутів
v1.3.1 - Route FSM: 9 станів, safety handling
v2.0.0 - System contract (acceptance-кейси)
v2.1.0 - Structured & Clarified (поточна версія)
         ├─ Чітка структура розділів
         ├─ Зафіксовано RELEASE_ON_FAULT = FALSE
         ├─ Детальна документація fault handling
         └─ Acceptance-кейси з гарантіями
```

### Додаток C: Посилання

```
contract_v2.0.0_system_contract.md    - попередня версія
design_rules_scada_plc_route_canon.md - архітектурні правила
route_fsm_canon.md                     - таблиця станів Route FSM
routes_db_help.md                      - довідка по DB та протоколу
```

---

## ✅ Changelog v2.1.0

```
[ADDED]
+ Section 1: Терміни та визначення (structured table)
+ Section 2.2: Потік виконання PLC циклу
+ Section 2.3: Slot-based addressing table
+ Section 7: Manual Control (повний розділ) ⭐
  ├─ Протокол обміну (commit-based)
  ├─ Workflow SCADA manual
  ├─ Reject codes та ManualAllowed
  ├─ Chunked processing
  ├─ Приклад повного циклу
  ├─ Fault handling в manual mode
  ├─ Взаємодія з Routes
  └─ Performance metrics та UI рекомендації
+ Section 9: Fault handling (повний розділ)
+ Section 9.3: Owner при fault (ключове правило)
+ Section 9.4: Recovery patterns (code examples)
+ Section 13: Гарантії та інваріанти
+ AC-05a/AC-05b: Fault scenarios (детально)
+ Додаток B: Версії контракту
+ Додаток C: Посилання

[CHANGED]
~ Section 2.1: Архітектура (додано Manual Control Handler)
~ Section 5.4: Звільнення Owner (чітка структура)
~ Section 10: Розподіл відповідальності (граничні закони)
~ Section 11: Політики (фіксовані vs конфігуровані)
~ Section 12: Acceptance-кейси (розширені з гарантіями)
~ Renumbered: розділи 7-12 → 8-13 (через додавання Manual Control)

[FIXED]
- Section 11.1: Видалено P2 з конфігурованих (це фіксована політика)
- Section 5.3: Уточнено "Fault (за політикою)" → "Fault НЕ звільняє owner"

[REMOVED]
- Невизначеність P2: RELEASE_ON_FAULT (зафіксовано FALSE)
```

---

**Кінець контракту v2.1.0**

🎯 **Цей контракт є єдиним джерелом істини для архітектури системи.**
