# Універсальний контракт керування механізмами елеватора

**Версія:** v2.0.0-system-contract (на базі v1.3.1-route-doublebuffer)  
**Статус:** ПРОЄКТ / ДЛЯ ФІКСАЦІЇ  

---

## 0. Терміни

**Slot** — індекс механізму в масиві(ах) DB. Єдиний ідентифікатор механізму в обміні.  

**Механізм** — типова сутність (редлер/норія/шнек/вентилятор/засувка тощо), реалізована як FB/FC пасивного типу.  

**HAL** — шар нормалізації фізичних сигналів (інверсії, fail-safe, реальний стан).  

**SCADA** — формує завдання, маршрути, ручні запити. Не керує I/O напряму.  

**PLC** — виконує механізми, арбітраж команд, виконання маршрутів, safety.  

---

## 1. Архітектура рівнів (незмінна основа)

### L0 — HAL
Приймає сирі входи/виходи, приводить до стандартизованих сигналів механізмів.

### L1 — Mechanism Layer (пасивні механізми)
- Кожен тип механізму — типовий FB/FC  
- Заповнює Status / FLTCode / LastCmd  
- Реагує на Cmd / CmdParam / Force_Code та Enable_OK / LocalManual  

### L2 — Device Runner (tick)
- Простий виклик усіх механізмів свого типу/групи  
- Без логіки маршрутів і без арбітражу  

### L3 — Control Intelligence
- Арбітраж доступу (Owner + право команди)  
- Виконання маршрутів (FSM)  
- Safety / Global interlocks  

---

## 2. Головні інваріанти системи

### 2.1 Заборона перетину механізмів між маршрутами
- SCADA може запускати кілька маршрутів одночасно  
- Один Slot не може належати більше ніж одному активному маршруту  
- PLC зобовʼязаний перевіряти це при старті маршруту  
- Порушення → маршрут **REJECTED**

### 2.2 Заборона ручного керування механізмом у маршруті
- Якщо OwnerCur = ROUTE → SCADA manual заборонено  
- Вплив можливий лише через керування маршрутом (Pause / Abort)

### 2.3 Локальне ручне керування (глобальне)
- Є глобальний сигнал **LocalManualGlobal**
- При LocalManualGlobal = 1:
  - PLC не видає RUN/START
  - маршрути переходять у ABORT
  - діагностика продовжується

---

## 3. Контракт механізму (мінімальний інтерфейс)

### 3.1 Дозволи / режими
- Enable_OK : BOOL  
- LocalManual : BOOL  

### 3.2 Ідентифікація
- DeviceType : USINT  

### 3.3 Команди
- Cmd : USINT  
- CmdParam1 : INT  
- Force_Code : INT  

### 3.4 Власник (арбітраж)
- OwnerCur : USINT  
- OwnerCurId : UINT  

### 3.5 Діагностика
- LastCmd : USINT  
- FLTCode : UINT  
- Status : UINT  

---

## 4. Команди та стани
Константи зберігаються в **DB_Const**:
- CMD_*  
- STS_*  
- FLT_*  
- TYPE_*  

---

## 5. Арбітраж команд

### 5.1 Єдине місце запису Cmd
Будь-яка команда проходить через арбітр. Прямий запис Cmd — порушення контракту.

### 5.2 Правила доступу
1. LocalManualGlobal = 1 → PLC не керує  
2. M.LocalManual = 1 → PLC не керує  
3. OwnerCur = 0 → власник може бути встановлений  
4. OwnerCur = ROUTE → SCADA manual заборонено  
5. Owner не співпадає → команда ігнорується  

### 5.3 Звільнення Owner
- DONE / ABORTED / REJECTED маршруту  
- Fault (за політикою)  
- SCADA release дозволено лише якщо OwnerCur = SCADA

---

## 6. Маршрути (SCADA → PLC, double buffer)

### 6.1 Принцип
SCADA формує маршрут, пише у DB (double buffer), робить COMMIT. PLC виконує автономно.

### 6.2 Паралельні маршрути
RouteId = 1..R, кожен має власний FSM.

### 6.3 Валідація
- існування slot
- коректний DeviceType - “slot замаплений (TYPE_NONE заборонено)”
- OwnerCur = 0 для всіх slot  
→ інакше **REJECTED_BY_CONTRACT**

### 6.4 Locking
- OwnerCur := ROUTE  
- OwnerCurId := RouteId  
- Lock атомарний

### 6.5 Виконання
- Route керує механізмами лише через арбітраж
- SCADA не керує slot напряму під час RUNNING

---

## 7. Safety та інтерлоки

### 7.1 Global Manual
LocalManualGlobal = 1 → ABORT (через STOPPING)

### 7.2 Аварійні сигнали
Safety може:
- форсувати STOP / Blocked
- переводити маршрути у ABORTED / FAULT

---

## 8. Ролі

### SCADA
- Формує маршрути
- Пише DB + COMMIT
- Відображає Owner / Status / Fault
- Блокує manual UI для slot у маршруті

### PLC
- HAL + Runner
- Арбітраж
- Route FSM
- Safety

---

## 9. Acceptance-кейси
1. Перетин маршрутів → REJECTED  
2. SCADA manual у маршруті → ігнор  
3. LocalManualGlobal під час RUNNING → STOP  
4. Повернення AUTO → початковий стан
5. Fault → FAULT / ABORTED + release owner

---

## 10. Config Policy (обовʼязково зафіксувати)
- **P1:** LocalManualGlobal → PAUSE або ABORT (рекомендовано PAUSE)  
- **P2:** RELEASE_ON_FAULT = TRUE / FALSE (рекомендовано TRUE)
