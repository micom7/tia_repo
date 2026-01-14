import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

class PLCCodeGenerator:
    """
    Генератор PLC коду з Excel конфігурації.
    Генерує:
    - DB_Mechs.scl (масиви механізмів)
    - FC_InitMechs.scl (ініціалізація мапінгу)
    - FC_DeviceRunner.scl (виконання механізмів)
    - DB_HAL_*.scl (мапінг I/O)
    - FC_HAL_*_Read.scl (читання входів)
    - FC_HAL_*_Write.scl (запис виходів)
    - Документація (Markdown, CSV)
    """
    
    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.config = {}
        self.redlers = []
        self.norias = []
        self.gates = []
        self.fans = []
        
    def load_excel(self):
        """Завантажити всі аркуші з Excel"""
        print(f"📖 Завантаження {self.excel_path}...")
        
        xls = pd.ExcelFile(self.excel_path)
        
        # Конфігурація
        df_config = pd.read_excel(xls, 'CONFIG')
        self.config = dict(zip(df_config['Parameter'], df_config['Value']))
        
        # Механізми (фільтруємо тільки Enabled=TRUE)
        self.redlers = pd.read_excel(xls, 'REDLERS').fillna('').to_dict('records')
        self.redlers = [r for r in self.redlers if r.get('Enabled') == True]
        
        self.norias = pd.read_excel(xls, 'NORIAS').fillna('').to_dict('records')
        self.norias = [n for n in self.norias if n.get('Enabled') == True]
        
        self.gates = pd.read_excel(xls, 'GATES').fillna('').to_dict('records')
        self.gates = [g for g in self.gates if g.get('Enabled') == True]
        
        self.fans = pd.read_excel(xls, 'FANS').fillna('').to_dict('records')
        self.fans = [f for f in self.fans if f.get('Enabled') == True]
        
        print(f"✅ Завантажено:")
        print(f"   - Редлерів: {len(self.redlers)}")
        print(f"   - Норій: {len(self.norias)}")
        print(f"   - Засувок: {len(self.gates)}")
        print(f"   - Вентиляторів: {len(self.fans)}")
    

    def validate_excel(self):
        """Валідація конфігурації"""
        errors = []
        warnings = []
        
        # Перевірка унікальності slot
        all_mechs = self.redlers + self.norias + self.gates + self.fans
        slots = [m['Slot'] for m in all_mechs]
        
        if len(slots) != len(set(slots)):
            slot_counts = {}
            for s in slots:
                slot_counts[s] = slot_counts.get(s, 0) + 1
            duplicates = [s for s, c in slot_counts.items() if c > 1]
            errors.append(f"❌ Дублікати slot: {duplicates}")
        
        # Перевірка діапазонів slot
        for r in self.redlers:
            if not (0 <= r['Slot'] <= 49):
                warnings.append(f"⚠️  Редлер '{r['Name']}' slot={r['Slot']} поза рекомендованим діапазоном 0-49")
        
        for n in self.norias:
            if not (50 <= n['Slot'] <= 99):
                warnings.append(f"⚠️  Норія '{n['Name']}' slot={n['Slot']} поза рекомендованим діапазоном 50-99")
        
        for g in self.gates:
            if not (100 <= g['Slot'] <= 149):
                warnings.append(f"⚠️  Засувка '{g['Name']}' slot={g['Slot']} поза рекомендованим діапазоном 100-149")
        
        for f in self.fans:
            if not (150 <= f['Slot'] <= 199):
                warnings.append(f"⚠️  Вентилятор '{f['Name']}' slot={f['Slot']} поза рекомендованим діапазоном 150-199")
        
        # Перевірка унікальності TypedIdx в межах типу
        if self.redlers:
            typed_idxs = [m['TypedIdx'] for m in self.redlers]
            if len(typed_idxs) != len(set(typed_idxs)):
                errors.append(f"❌ Дублікати TypedIdx у редлерах")
        
        if self.norias:
            typed_idxs = [m['TypedIdx'] for m in self.norias]
            if len(typed_idxs) != len(set(typed_idxs)):
                errors.append(f"❌ Дублікати TypedIdx у норіях")
        
        if self.gates:
            typed_idxs = [m['TypedIdx'] for m in self.gates]
            if len(typed_idxs) != len(set(typed_idxs)):
                errors.append(f"❌ Дублікати TypedIdx у засувках")
        
        if self.fans:
            typed_idxs = [m['TypedIdx'] for m in self.fans]
            if len(typed_idxs) != len(set(typed_idxs)):
                errors.append(f"❌ Дублікати TypedIdx у вентиляторах")
        
        # Перевірка унікальності I/O адрес
        io_addrs = {}
        for m in all_mechs:
            for key, val in m.items():
                # ВИПРАВЛЕНО: перевіряємо, що key це рядок
                if isinstance(key, str) and key.startswith(('DI_', 'DO_')) and val and val != '':
                    if val in io_addrs:
                        errors.append(f"❌ Конфлікт I/O: {val} використовується у '{io_addrs[val]}' та '{m['Name']}'")
                    else:
                        io_addrs[val] = m['Name']
        
        # Вивести попередження
        for w in warnings:
            print(w)
        
        # Перевірити помилки
        if errors:
            for e in errors:
                print(e)
            raise ValueError("❌ Валідація не пройдена!")
        
        print("✅ Валідація пройдена")





    def _get_header(self, title: str, family: str = "") -> str:
        """Генерація заголовку SCL файлу"""
        return f'''// ============================================================================
// {title}
// ============================================================================
// Project  : {self.config.get('ProjectName', 'Unknown')}
// Author   : {self.config.get('Author', 'AutoGen')}
// Version  : {self.config.get('Version', '1.0.0')}
// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// ============================================================================
'''
    
    def generate_db_mechs(self) -> str:
        """Генерація DB_Mechs.scl"""
        max_redlers = max([r['TypedIdx'] for r in self.redlers], default=-1) + 1 if self.redlers else 0
        max_norias = max([n['TypedIdx'] for n in self.norias], default=-1) + 1 if self.norias else 0
        max_gates = max([g['TypedIdx'] for g in self.gates], default=-1) + 1 if self.gates else 0
        max_fans = max([f['TypedIdx'] for f in self.fans], default=-1) + 1 if self.fans else 0
        
        code = self._get_header("DB_Mechs - Масиви механізмів", "MechData")
        code += '''
DATA_BLOCK "DB_Mechs"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

VAR
    // ===================================================================
    // Базова шина механізмів (усі слоти 0..255)
    // - Команди, статус, owner
    // - Використовується для арбітражу, маршрутів, SCADA
    // ===================================================================
    Mechs : ARRAY [0..255] OF "UDT_BaseMechanism";
    
'''
        
        # Додати типізовані масиви
        if max_redlers > 0:
            code += f'''    // ===================================================================
    // Редлери (типізовані, специфіка HAL)
    // Кількість: {len(self.redlers)} активних, масив [0..{max_redlers-1}]
    // ===================================================================
    Redler : ARRAY [0..{max_redlers-1}] OF "UDT_Redler";
    
'''
        
        if max_norias > 0:
            code += f'''    // ===================================================================
    // Норії (типізовані, специфіка HAL)
    // Кількість: {len(self.norias)} активних, масив [0..{max_norias-1}]
    // ===================================================================
    Noria : ARRAY [0..{max_norias-1}] OF "UDT_Noria";
    
'''
        
        if max_gates > 0:
            code += f'''    // ===================================================================
    // Засувки (типізовані, специфіка HAL)
    // Кількість: {len(self.gates)} активних, масив [0..{max_gates-1}]
    // ===================================================================
    Gate : ARRAY [0..{max_gates-1}] OF "UDT_Gate";
    
'''
        
        if max_fans > 0:
            code += f'''    // ===================================================================
    // Вентилятори (типізовані, специфіка HAL)
    // Кількість: {len(self.fans)} активних, масив [0..{max_fans-1}]
    // ===================================================================
    Fan : ARRAY [0..{max_fans-1}] OF "UDT_Fan";
    
'''
        
        code += '''END_VAR

BEGIN
    // Ініціалізація виконується при старті через FC_InitMechs (OB100)
END_DATA_BLOCK
'''
        return code
    
    def generate_fc_init_mechs(self) -> str:
        """Генерація FC_InitMechs.scl - ініціалізація мапінгу slot → type/idx"""
        code = self._get_header("FC_InitMechs - Ініціалізація мапінгу механізмів", "Init")
        code += '''
FUNCTION "FC_InitMechs" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

// ============================================================================
// ВИКЛИКАТИ ОДИН РАЗ ПРИ СТАРТІ PLC (OB100)
// ============================================================================
// Ініціалізує DeviceType та TypedIndex для всіх механізмів.
// Порожні слоти залишаються з DeviceType=TYPE_NONE (0).
// ============================================================================

VAR_TEMP
    i : INT;
END_VAR

BEGIN
    // ===================================================================
    // КРОК 1: Очистити ВСІ слоти (за замовчуванням = порожні)
    // ===================================================================
    FOR i := 0 TO 255 DO
        "DB_Mechs".Mechs[i].DeviceType := "DB_Const".TYPE_NONE;
        "DB_Mechs".Mechs[i].TypedIndex := UINT#16#FFFF;
    END_FOR;
    
    // ===================================================================
    // КРОК 2: Ініціалізувати ТІЛЬКИ активні слоти
    // ===================================================================
    
'''
        
        # Редлери
        if self.redlers:
            code += "    // === REDLERS ===\n"
            for r in self.redlers:
                slot = r['Slot']
                idx = r['TypedIdx']
                name = r['Name']
                location = r['Location']
                code += f"    \"DB_Mechs\".Mechs[{slot}].DeviceType := \"DB_Const\".TYPE_REDLER;  // {name} ({location})\n"
                code += f"    \"DB_Mechs\".Mechs[{slot}].TypedIndex := {idx};\n"
                code += "\n"
        
        # Норії
        if self.norias:
            code += "    // === NORIAS ===\n"
            for n in self.norias:
                slot = n['Slot']
                idx = n['TypedIdx']
                name = n['Name']
                location = n['Location']
                code += f"    \"DB_Mechs\".Mechs[{slot}].DeviceType := \"DB_Const\".TYPE_NORIA;  // {name} ({location})\n"
                code += f"    \"DB_Mechs\".Mechs[{slot}].TypedIndex := {idx};\n"
                code += "\n"
        
        # Засувки
        if self.gates:
            code += "    // === GATES ===\n"
            for g in self.gates:
                slot = g['Slot']
                idx = g['TypedIdx']
                name = g['Name']
                location = g['Location']
                code += f"    \"DB_Mechs\".Mechs[{slot}].DeviceType := \"DB_Const\".TYPE_GATE2P;  // {name} ({location})\n"
                code += f"    \"DB_Mechs\".Mechs[{slot}].TypedIndex := {idx};\n"
                code += "\n"
        
        # Вентилятори
        if self.fans:
            code += "    // === FANS ===\n"
            for f in self.fans:
                slot = f['Slot']
                idx = f['TypedIdx']
                name = f['Name']
                location = f['Location']
                code += f"    \"DB_Mechs\".Mechs[{slot}].DeviceType := \"DB_Const\".TYPE_FAN;  // {name} ({location})\n"
                code += f"    \"DB_Mechs\".Mechs[{slot}].TypedIndex := {idx};\n"
                code += "\n"
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_fc_device_runner(self) -> str:
        """Генерація FC_DeviceRunner.scl з діапазонами"""
        code = self._get_header("FC_DeviceRunner - Виконання механізмів", "Runner")
        code += '''
FUNCTION "FC_DeviceRunner" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

// ============================================================================
// ВИКЛИКАТИ У ЦИКЛІ OB1
// ============================================================================
// Виконує всі активні механізми за типами.
// Порожні слоти (DeviceType=TYPE_NONE) автоматично пропускаються.
// ============================================================================

VAR_IN_OUT
    Mechs  : ARRAY[*] OF "UDT_BaseMechanism";
'''
        
        if self.redlers:
            code += '    Redler : ARRAY[*] OF "UDT_Redler";\n'
        if self.norias:
            code += '    Noria  : ARRAY[*] OF "UDT_Noria";\n'
        if self.gates:
            code += '    Gate   : ARRAY[*] OF "UDT_Gate";\n'
        if self.fans:
            code += '    Fan    : ARRAY[*] OF "UDT_Fan";\n'
        
        code += '''END_VAR

VAR_TEMP
    slot : INT;
    idx  : INT;
END_VAR

BEGIN
'''
        
        # Редлери
        if self.redlers:
            min_slot = min([r['Slot'] for r in self.redlers])
            max_slot = max([r['Slot'] for r in self.redlers])
            code += f'''    // ===================================================================
    // REDLERS (діапазон slot: {min_slot}..{max_slot})
    // Активних: {len(self.redlers)}
    // ===================================================================
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_REDLER THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Redler"(R := Redler[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        # Норії
        if self.norias:
            min_slot = min([n['Slot'] for n in self.norias])
            max_slot = max([n['Slot'] for n in self.norias])
            code += f'''    // ===================================================================
    // NORIAS (діапазон slot: {min_slot}..{max_slot})
    // Активних: {len(self.norias)}
    // ===================================================================
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_NORIA THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Noria"(N := Noria[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        # Засувки
        if self.gates:
            min_slot = min([g['Slot'] for g in self.gates])
            max_slot = max([g['Slot'] for g in self.gates])
            code += f'''    // ===================================================================
    // GATES (діапазон slot: {min_slot}..{max_slot})
    // Активних: {len(self.gates)}
    // ===================================================================
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_GATE2P THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Gate"(G := Gate[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        # Вентилятори
        if self.fans:
            min_slot = min([f['Slot'] for f in self.fans])
            max_slot = max([f['Slot'] for f in self.fans])
            code += f'''    // ===================================================================
    // FANS (діапазон slot: {min_slot}..{max_slot})
    // Активних: {len(self.fans)}
    // ===================================================================
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_FAN THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Fan"(F := Fan[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_db_hal_redler(self) -> str:
        """Генерація DB_HAL_Redler.scl"""
        if not self.redlers:
            return ""
        
        code = self._get_header("DB_HAL_Redler - Мапінг I/O редлерів", "HAL")
        code += '''
DATA_BLOCK "DB_HAL_Redler"
{ S7_Optimized_Access := 'FALSE' }  // AT вимагає вимкненої оптимізації
VERSION : 1.0

VAR
'''
        
        for r in self.redlers:
            idx = r['TypedIdx']
            name = r['Name']
            location = r['Location']
            
            code += f'''
    // ===================================================================
    // {name} (TypedIdx={idx})
    // Slot: {r['Slot']} | {location}
    // ===================================================================
    DI_Speed_{idx}    AT {r['DI_Speed']}    : BOOL;  // Тахо-датчик (1=норма)
    DI_Breaker_{idx}  AT {r['DI_Breaker']}  : BOOL;  // Автомат захисту (1=увімкнено)
    DI_Overflow_{idx} AT {r['DI_Overflow']} : BOOL;  // Датчик переповнення (1=OK)
    DO_Run_{idx}      AT {r['DO_Run']}      : BOOL;  // Контактор пуску (1=пуск)
'''
        
        code += '''
END_VAR

BEGIN
END_DATA_BLOCK
'''
        return code
    
    def generate_fc_hal_redler_read(self) -> str:
        """Генерація FC_HAL_Redler_Read.scl"""
        if not self.redlers:
            return ""
        
        code = self._get_header("FC_HAL_Redler_Read - Читання HAL входів редлерів", "HAL")
        code += '''
FUNCTION "FC_HAL_Redler_Read" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

// ============================================================================
// ВИКЛИКАТИ У ЦИКЛІ OB1 ПЕРЕД FC_DeviceRunner
// ============================================================================
// Копіює фізичні входи (DB_HAL_Redler) → структури Redler[]
// ============================================================================

VAR_IN_OUT
    Redler : ARRAY[*] OF "UDT_Redler";
END_VAR

BEGIN
'''
        
        for r in self.redlers:
            idx = r['TypedIdx']
            name = r['Name']
            code += f'''    // {name}
    Redler[{idx}].DI_Speed_OK    := "DB_HAL_Redler".DI_Speed_{idx};
    Redler[{idx}].DI_Breaker_OK  := "DB_HAL_Redler".DI_Breaker_{idx};
    Redler[{idx}].DI_Overflow_OK := "DB_HAL_Redler".DI_Overflow_{idx};
    
'''
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_fc_hal_redler_write(self) -> str:
        """Генерація FC_HAL_Redler_Write.scl"""
        if not self.redlers:
            return ""
        
        code = self._get_header("FC_HAL_Redler_Write - Запис HAL виходів редлерів", "HAL")
        code += '''
FUNCTION "FC_HAL_Redler_Write" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

// ============================================================================
// ВИКЛИКАТИ У ЦИКЛІ OB1 ПІСЛЯ FC_DeviceRunner
// ============================================================================
// Копіює структури Redler[] → фізичні виходи (DB_HAL_Redler)
// ============================================================================

VAR_IN_OUT
    Redler : ARRAY[*] OF "UDT_Redler";
END_VAR

BEGIN
'''
        
        for r in self.redlers:
            idx = r['TypedIdx']
            name = r['Name']
            code += f'''    // {name}
    "DB_HAL_Redler".DO_Run_{idx} := Redler[{idx}].DO_Run;
    
'''
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_documentation_md(self) -> str:
        """Генерація документації Markdown"""
        total_mechs = len(self.redlers) + len(self.norias) + len(self.gates) + len(self.fans)
        
        doc = f'''# Конфігурація механізмів

**Проект:** {self.config.get('ProjectName', 'Unknown')}  
**Версія:** {self.config.get('Version', '1.0.0')}  
**Автор:** {self.config.get('Author', 'AutoGen')}  
**Дата генерації:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Загальна статистика

- **Усього механізмів:** {total_mechs}
  - Редлерів: {len(self.redlers)}
  - Норій: {len(self.norias)}
  - Засувок: {len(self.gates)}
  - Вентиляторів: {len(self.fans)}

---

## Діапазони slot

| Тип механізму | Рекомендований діапазон | Фактичний діапазон |
|---------------|--------------------------|---------------------|
'''
        
        if self.redlers:
            min_slot = min([r['Slot'] for r in self.redlers])
            max_slot = max([r['Slot'] for r in self.redlers])
            doc += f"| Редлери | 0-49 | {min_slot}-{max_slot} |\n"
        
        if self.norias:
            min_slot = min([n['Slot'] for n in self.norias])
            max_slot = max([n['Slot'] for n in self.norias])
            doc += f"| Норії | 50-99 | {min_slot}-{max_slot} |\n"
        
        if self.gates:
            min_slot = min([g['Slot'] for g in self.gates])
            max_slot = max([g['Slot'] for g in self.gates])
            doc += f"| Засувки | 100-149 | {min_slot}-{max_slot} |\n"
        
        if self.fans:
            min_slot = min([f['Slot'] for f in self.fans])
            max_slot = max([f['Slot'] for f in self.fans])
            doc += f"| Вентилятори | 150-199 | {min_slot}-{max_slot} |\n"
        
        doc += "\n---\n\n"
        
        # Редлери
        if self.redlers:
            doc += "## Редлери\n\n"
            doc += "| Slot | TypedIdx | Name | Location | I/O | Timeouts |\n"
            doc += "|------|----------|------|----------|-----|----------|\n"
            
            for r in sorted(self.redlers, key=lambda x: x['Slot']):
                io_str = f"IN: {r['DI_Speed']}, {r['DI_Breaker']}, {r['DI_Overflow']} / OUT: {r['DO_Run']}"
                timeout_str = f"Start: {r['StartTimeout']}ms, Speed: {r['SpeedTimeout']}ms"
                doc += f"| {r['Slot']} | {r['TypedIdx']} | {r['Name']} | {r['Location']} | {io_str} | {timeout_str} |\n"
            
            doc += "\n"
        
        # Норії
        if self.norias:
            doc += "## Норії\n\n"
            doc += "| Slot | TypedIdx | Name | Location | I/O | Timeout |\n"
            doc += "|------|----------|------|----------|-----|----------|\n"
            
            for n in sorted(self.norias, key=lambda x: x['Slot']):
                io_str = f"IN: {n['DI_Speed']}, {n['DI_Breaker']}, {n['DI_UpperLevel']}, {n['DI_LowerLevel']} / OUT: {n['DO_Run']}"
                doc += f"| {n['Slot']} | {n['TypedIdx']} | {n['Name']} | {n['Location']} | {io_str} | {n['StartTimeout']}ms |\n"
            
            doc += "\n"
        
        # Засувки
        if self.gates:
            doc += "## Засувки\n\n"
            doc += "| Slot | TypedIdx | Name | Location | I/O | Timeout |\n"
            doc += "|------|----------|------|----------|-----|----------|\n"
            
            for g in sorted(self.gates, key=lambda x: x['Slot']):
                io_str = f"IN: {g['DI_Opened']}, {g['DI_Closed']} / OUT: {g['DO_Open']}, {g['DO_Close']}"
                doc += f"| {g['Slot']} | {g['TypedIdx']} | {g['Name']} | {g['Location']} | {io_str} | {g['MoveTimeout']}ms |\n"
            
            doc += "\n"
        
        # Вентилятори
        if self.fans:
            doc += "## Вентилятори\n\n"
            doc += "| Slot | TypedIdx | Name | Location | I/O |\n"
            doc += "|------|----------|------|----------|-----|\n"
            
            for f in sorted(self.fans, key=lambda x: x['Slot']):
                io_str = f"IN: {f['DI_Breaker']} / OUT: {f['DO_Run']}"
                doc += f"| {f['Slot']} | {f['TypedIdx']} | {f['Name']} | {f['Location']} | {io_str} |\n"
            
            doc += "\n"
        
        # Додати інструкції інтеграції
        doc += '''---

## Інтеграція у PLC

### OB100 (Startup)
```scl
// Викликати ОДИН РАЗ при старті PLC
"FC_InitMechs"();
```

### OB1 (Cyclic)
```scl
// 1. Читання HAL входів
'''
        
        if self.redlers:
            doc += '''"FC_HAL_Redler_Read"(Redler := "DB_Mechs".Redler);
'''
        
        doc += '''
// 2. Виконання механізмів
"FC_DeviceRunner"(
    Mechs  := "DB_Mechs".Mechs'''
        
        if self.redlers:
            doc += ''',
    Redler := "DB_Mechs".Redler'''
        if self.norias:
            doc += ''',
    Noria  := "DB_Mechs".Noria'''
        if self.gates:
            doc += ''',
    Gate   := "DB_Mechs".Gate'''
        if self.fans:
            doc += ''',
    Fan    := "DB_Mechs".Fan'''
        
        doc += '''
);

// 3. Запис HAL виходів
'''
        
        if self.redlers:
            doc += '''"FC_HAL_Redler_Write"(Redler := "DB_Mechs".Redler);
'''
        
        doc += '''```
'''
        
        return doc
    
    def generate_io_list_csv(self) -> str:
        """Генерація списку I/O у CSV форматі"""
        lines = ["Address,Type,MechType,Slot,TypedIdx,Name,Description,Location\n"]
        
        # Редлери
        for r in sorted(self.redlers, key=lambda x: x['Slot']):
            lines.append(f"{r['DI_Speed']},DI,REDLER,{r['Slot']},{r['TypedIdx']},{r['Name']}_Speed,Тахо-датчик,{r['Location']}\n")
            lines.append(f"{r['DI_Breaker']},DI,REDLER,{r['Slot']},{r['TypedIdx']},{r['Name']}_Breaker,Автомат захисту,{r['Location']}\n")
            lines.append(f"{r['DI_Overflow']},DI,REDLER,{r['Slot']},{r['TypedIdx']},{r['Name']}_Overflow,Датчик переповнення,{r['Location']}\n")
            lines.append(f"{r['DO_Run']},DO,REDLER,{r['Slot']},{r['TypedIdx']},{r['Name']}_Run,Контактор пуску,{r['Location']}\n")
        
        # Норії
        for n in sorted(self.norias, key=lambda x: x['Slot']):
            lines.append(f"{n['DI_Speed']},DI,NORIA,{n['Slot']},{n['TypedIdx']},{n['Name']}_Speed,Тахо-датчик,{n['Location']}\n")
            lines.append(f"{n['DI_Breaker']},DI,NORIA,{n['Slot']},{n['TypedIdx']},{n['Name']}_Breaker,Автомат захисту,{n['Location']}\n")
            lines.append(f"{n['DI_UpperLevel']},DI,NORIA,{n['Slot']},{n['TypedIdx']},{n['Name']}_Upper,Верхній рівень,{n['Location']}\n")
            lines.append(f"{n['DI_LowerLevel']},DI,NORIA,{n['Slot']},{n['TypedIdx']},{n['Name']}_Lower,Нижній рівень,{n['Location']}\n")
            lines.append(f"{n['DO_Run']},DO,NORIA,{n['Slot']},{n['TypedIdx']},{n['Name']}_Run,Контактор пуску,{n['Location']}\n")
        
        # Засувки
        for g in sorted(self.gates, key=lambda x: x['Slot']):
            lines.append(f"{g['DI_Opened']},DI,GATE,{g['Slot']},{g['TypedIdx']},{g['Name']}_Opened,Відкрита,{g['Location']}\n")
            lines.append(f"{g['DI_Closed']},DI,GATE,{g['Slot']},{g['TypedIdx']},{g['Name']}_Closed,Закрита,{g['Location']}\n")
            lines.append(f"{g['DO_Open']},DO,GATE,{g['Slot']},{g['TypedIdx']},{g['Name']}_Open,Відкрити,{g['Location']}\n")
            lines.append(f"{g['DO_Close']},DO,GATE,{g['Slot']},{g['TypedIdx']},{g['Name']}_Close,Закрити,{g['Location']}\n")
        
        # Вентилятори
        for f in sorted(self.fans, key=lambda x: x['Slot']):
            lines.append(f"{f['DI_Breaker']},DI,FAN,{f['Slot']},{f['TypedIdx']},{f['Name']}_Breaker,Автомат захисту,{f['Location']}\n")
            lines.append(f"{f['DO_Run']},DO,FAN,{f['Slot']},{f['TypedIdx']},{f['Name']}_Run,Пуск,{f['Location']}\n")
        
        return ''.join(lines)
    
    def generate_all(self, output_dir: str = "./generated"):
        """Генерувати всі файли"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"\n📝 Генерація файлів у {output_path}...\n")
        
        files_created = []
        
        # Основні DB/FC
        self._write_file(output_path / "DB_Mechs.scl", self.generate_db_mechs(), files_created)
        self._write_file(output_path / "FC_InitMechs.scl", self.generate_fc_init_mechs(), files_created)
        self._write_file(output_path / "FC_DeviceRunner.scl", self.generate_fc_device_runner(), files_created)
        
        # HAL Redler
        if self.redlers:
            self._write_file(output_path / "DB_HAL_Redler.scl", self.generate_db_hal_redler(), files_created)
            self._write_file(output_path / "FC_HAL_Redler_Read.scl", self.generate_fc_hal_redler_read(), files_created)
            self._write_file(output_path / "FC_HAL_Redler_Write.scl", self.generate_fc_hal_redler_write(), files_created)
        
        # TODO: HAL для інших типів (Noria, Gate, Fan)
        
        # Документація
        self._write_file(output_path / "CONFIG_DOCUMENTATION.md", self.generate_documentation_md(), files_created)
        self._write_file(output_path / "IO_LIST.csv", self.generate_io_list_csv(), files_created)
        
        print(f"\n✅ Згенеровано {len(files_created)} файлів:")
        for f in files_created:
            print(f"   ✓ {f}")
        
        print(f"\n📂 Файли збережено у: {output_path.absolute()}")
    
    def _write_file(self, path: Path, content: str, files_list: List[str]):
        """Записати файл та додати до списку"""
        if content:
            path.write_text(content, encoding='utf-8')
            files_list.append(path.name)


# ============================================================================
# Використання
# ============================================================================
if __name__ == "__main__":
    try:
        generator = PLCCodeGenerator("elevator_config.xlsx")
        generator.load_excel()
        generator.validate_excel()
        generator.generate_all("./generated")
        
        print("\n" + "="*70)
        print("🎉 Генерація завершена успішно!")
        print("="*70)
        
    except FileNotFoundError as e:
        print(f"\n❌ Помилка: файл 'elevator_config.xlsx' не знайдено")
        print(f"   Переконайся, що файл знаходиться у тій самій папці, що й скрипт")
        
    except ValueError as e:
        print(f"\n❌ Помилка валідації: {e}")
        
    except Exception as e:
        print(f"\n❌ Несподівана помилка: {e}")
        import traceback
        traceback.print_exc()
'''

---

## Шаблон Excel файлу: `elevator_config.xlsx`

### Аркуш "CONFIG"

| Parameter | Value | Description |
|-----------|-------|-------------|
| ProjectName | Elevator_System | Назва проекту |
| MaxSlots | 256 | Максимум слотів |
| Author | Engineering Team | Автор |
| Version | 1.0.0 | Версія конфігурації |

### Аркуш "REDLERS"

| Name | Description | Slot | TypedIdx | Location | DI_Speed | DI_Breaker | DI_Overflow | DO_Run | StartTimeout | SpeedTimeout | Enabled | Comment |
|------|-------------|------|----------|----------|----------|------------|-------------|--------|--------------|--------------|---------|---------|
| Редлер_1 | Підсилосний редлер №1 | 0 | 0 | Силос 1, Підвал | %I0.0 | %I0.1 | %I0.2 | %Q0.0 | 5000 | 2000 | TRUE | |
| Редлер_2 | Підсилосний редлер №2 | 1 | 1 | Силос 2, Підвал | %I0.3 | %I0.4 | %I0.5 | %Q0.1 | 5000 | 2000 | TRUE | |

### Аркуш "NORIAS"

| Name | Description | Slot | TypedIdx | Location | DI_Speed | DI_Breaker | DI_UpperLevel | DI_LowerLevel | DO_Run | StartTimeout | Enabled | Comment |
|------|-------------|------|----------|----------|----------|------------|---------------|---------------|--------|--------------|---------|---------|
| Норія_1 | Норія башти №1 | 50 | 0 | Башта 1 | %I2.0 | %I2.1 | %I2.2 | %I2.3 | %Q2.0 | 10000 | TRUE | |

### Аркуш "GATES"

| Name | Description | Slot | TypedIdx | Location | DI_Opened | DI_Closed | DO_Open | DO_Close | MoveTimeout | Enabled | Comment |
|------|-------------|------|----------|----------|-----------|-----------|---------|----------|-------------|---------|---------|
| Засувка_1 | Вихід силосу 1 | 100 | 0 | Силос 1, Низ | %I3.0 | %I3.1 | %Q3.0 | %Q3.1 | 15000 | TRUE | |

### Аркуш "FANS"

| Name | Description | Slot | TypedIdx | Location | DI_Breaker | DO_Run | Enabled | Comment |
|------|-------------|------|----------|----------|------------|--------|---------|---------|
| Вентилятор_1 | Вентиляція силосу 1 | 150 | 0 | Силос 1, Верх | %I4.0 | %Q4.0 | TRUE | |

---

## Запуск
```bash
# 1. Встановити бібліотеки (один раз)
pip install pandas openpyxl

# 2. Запустити генератор
python generate_plc_config.py
```

---
'''