Довідка: маршрути PLC (SCADA → PLC) — фактична реалізація
Загальні принципи (як є зараз)

Маршрут = індекс i (1..12)

SCADA керує тільки командами і описом кроків

PLC повністю керує виконанням, FSM, арбітражем і статусами

Механізми адресуються через slot (0..255)

Слот вважається валідним, якщо:

DeviceType <> TYPE_NONE

TypedIndex <> 16#FFFF

1) DB_ScadaToPlc_RouteCmd

Призначення: передача маршрутних команд і кроків від SCADA до PLC
Тип доступу: SCADA → PLC (PLC тільки читає)

Структура

HDR_ActiveBuf : USINT — активний буфер (0 або 1)

HDR_Commit : UDINT — лічильник змін (SCADA інкрементує)

Буфери маршрутів

BUF0_Routes[1..12] : UDT_RouteCmd

BUF1_Routes[1..12] : UDT_RouteCmd

Правило запису SCADA (double buffer)

SCADA записує маршрутні дані (Cmd + Steps) у неактивний буфер

Після повного запису атомарно:

перемикає HDR_ActiveBuf

інкрементує HDR_Commit

PLC не аналізує зміст буфера, лише використовує його як джерело команд.

2) DB_Plc_RouteFsm

Призначення: збереження внутрішнього стану FSM маршрутів
Тип доступу: тільки PLC

Структура

RoutesFsm[1..12] : UDT_RouteFsmState

Важливо

Уся памʼять FSM маршруту зберігається в цьому DB

FB_RouteFSM отримує Fsm як VAR_IN_OUT

SCADA сюди не пише

FSM маршруту є станом PLC, а не частиною команди.

3) DB_PlcToScada_RouteStatus

Призначення: передача станів і результатів маршрутів у SCADA
Тип доступу: PLC → SCADA (SCADA тільки читає)

Структура

ACK_CommitApplied : UDINT — останній commit, який PLC прийняв

RoutesSts[1..12] : UDT_RouteStatus

Поведінка

PLC оновлює статус кожного маршруту на кожному циклі

ACK_CommitApplied оновлюється після того, як PLC почало працювати з новим HDR_Commit

4) Як PLC реально використовує буфери (по факту)

PLC порівнює:

HDR_Commit != ACK_CommitApplied


Якщо є новий commit:

PLC бере HDR_ActiveBuf як єдине джерело маршрутних команд

Для кожного маршруту i = 1..12:

Cmd := BUF<ActiveBuf>_Routes[i]

Fsm := RoutesFsm[i]

Sts := RoutesSts[i]

викликає FB_RouteFSM

Після цього PLC:

встановлює ACK_CommitApplied := HDR_Commit

PLC не копіює команди у внутрішні DB, а працює з ними напряму через буфер.

5) Поведінка FB_RouteFSM (фактична)
FSM виконує:

валідацію маршрутів

атомарний lock механізмів через FC_ArbiterMech

поетапний START / STOP механізмів

контроль RUNNING / IDLE

аварійне зупинення

звільнення ownership

FSM НЕ робить:

не керує фізичними механізмами напряму

не перевіряє тип механізму (це робить runner)

не зберігає команд у памʼяті (Cmd — завжди зовнішній)

6) Взаємодія з механізмами (через слот)

FB_RouteFSM працює тільки з Mechs[slot] : UDT_BaseMechanism

Перед виконанням:

перевіряє, що слот замаплений

перевіряє Enable_OK, LocalManual, FLTCode, OwnerCur

Керування виконується через FC_ArbiterMech

Фізичне виконання — через FC_DeviceRunner → FC_Redler

7) Інваріанти (гарантії системи)

Єдине джерело команд механізму — FC_ArbiterMech

Єдине джерело стану механізму — Mechs[slot]

FSM маршруту не пише напряму Cmd у механізм

Маршрут не може керувати “порожнім” слотом

LocalManual / Safety мають вищий пріоритет за маршрут

8) Що важливо знати SCADA (без деталей реалізації)

SCADA не чекає миттєвого виконання

SCADA орієнтується тільки на RoutesSts[i]

Повторний START під час активного маршруту → REJECTED

Маршрут або:

DONE

REJECTED

ABORTED (operator / local / fault / safety)