#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PLC Code Generator v3.0 - З символьною адресацією (TIA Portal Tags)
Версія: 3.0.0
Дата: 2026-01-14

Генерує:
- DB_Mechs.scl (масиви механізмів)
- FC_InitMechs.scl (ініціалізація мапінгу)
- FC_DeviceRunner.scl (виконання механізмів)
- FC_HAL_Read.scl (читання через символьні імена)
- FC_HAL_Write.scl (запис через символьні імена)
- PLC_Tags.xlsx (таблиця тегів для імпорту в TIA Portal)
- Документація (Markdown, CSV)
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple

class PLCCodeGenerator:
    """Генератор PLC коду з Excel конфігурації"""
    
    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.config = {}
        self.redlers = []
        self.norias = []
        self.gates = []
        self.fans = []
        self.tags = []  # Список тегів для таблиці
        
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
        
        # Перевірка унікальності TypedIdx в межах типу
        for mech_type, mechs in [('Редлери', self.redlers), ('Норії', self.norias), 
                                  ('Засувки', self.gates), ('Вентилятори', self.fans)]:
            if mechs:
                typed_idxs = [m['TypedIdx'] for m in mechs]
                if len(typed_idxs) != len(set(typed_idxs)):
                    errors.append(f"❌ Дублікати TypedIdx у {mech_type}")
        
        # Перевірка унікальності I/O адрес
        io_addrs = {}
        for m in all_mechs:
            for key, val in m.items():
                if isinstance(key, str) and key.startswith(('DI_', 'DO_')) and val and val != '':
                    if val in io_addrs:
                        errors.append(f"❌ Конфлікт I/O: {val} використовується у '{io_addrs[val]}' та '{m['Name']}'")
                    else:
                        io_addrs[val] = m['Name']
        
        # Перевірити помилки
        if errors:
            for e in errors:
                print(e)
            raise ValueError("❌ Валідація не пройдена!")
        
        for w in warnings:
            print(w)
        
        print("✅ Валідація пройдена")
    
    def _get_header(self, title: str) -> str:
        """Генерація заголовку SCL файлу"""
        return f'''// ==============================================================================
// {title}
// ==============================================================================
// Project  : {self.config.get('ProjectName', 'Unknown')}
// Author   : {self.config.get('Author', 'AutoGen')}
// Version  : {self.config.get('Version', '1.0.0')}
// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// ==============================================================================
'''
    
    def _create_tag_name(self, mech_type: str, typed_idx: int, signal: str) -> str:
        """Створити символьне ім'я тега"""
        # typed_idx -> 1-based для імені
        return f"{mech_type}_{typed_idx + 1}_{signal}"
    
    def _add_tag(self, name: str, address: str, comment: str):
        """Додати тег до списку"""
        self.tags.append({
            'Name': name,
            'Path': 'IO_tags',
            'Data Type': 'Bool',
            'Logical Address': address,
            'Comment': comment,
            'Hmi Visible': True,
            'Hmi Accessible': True,
            'Hmi Writeable': True,
            'Typeobject ID': '',
            'Version ID': ''
        })
    
    def build_tags_table(self):
        """Побудувати таблицю тегів з усіх механізмів"""
        self.tags = []
        
        # Редлери
        for r in sorted(self.redlers, key=lambda x: x['TypedIdx']):
            idx = r['TypedIdx']
            name_base = r['Name'].replace(' ', '_')
            
            if r.get('DI_Speed'):
                tag_name = self._create_tag_name('Redler', idx, 'DI_Speed')
                self._add_tag(tag_name, r['DI_Speed'], f"{r['Name']} - Тахо-датчик ({r['Location']})")
            
            if r.get('DI_Breaker'):
                tag_name = self._create_tag_name('Redler', idx, 'DI_Breaker')
                self._add_tag(tag_name, r['DI_Breaker'], f"{r['Name']} - Автомат захисту ({r['Location']})")
            
            if r.get('DI_Overflow'):
                tag_name = self._create_tag_name('Redler', idx, 'DI_Overflow')
                self._add_tag(tag_name, r['DI_Overflow'], f"{r['Name']} - Переповнення ({r['Location']})")
            
            if r.get('DO_Run'):
                tag_name = self._create_tag_name('Redler', idx, 'DO_Run')
                self._add_tag(tag_name, r['DO_Run'], f"{r['Name']} - Контактор пуску ({r['Location']})")
        
        # Норії
        for n in sorted(self.norias, key=lambda x: x['TypedIdx']):
            idx = n['TypedIdx']
            
            if n.get('DI_Speed'):
                tag_name = self._create_tag_name('Noria', idx, 'DI_Speed')
                self._add_tag(tag_name, n['DI_Speed'], f"{n['Name']} - Тахо-датчик ({n['Location']})")
            
            if n.get('DI_Breaker'):
                tag_name = self._create_tag_name('Noria', idx, 'DI_Breaker')
                self._add_tag(tag_name, n['DI_Breaker'], f"{n['Name']} - Автомат захисту ({n['Location']})")
            
            if n.get('DI_UpperLevel'):
                tag_name = self._create_tag_name('Noria', idx, 'DI_UpperLevel')
                self._add_tag(tag_name, n['DI_UpperLevel'], f"{n['Name']} - Верхній рівень ({n['Location']})")
            
            if n.get('DI_LowerLevel'):
                tag_name = self._create_tag_name('Noria', idx, 'DI_LowerLevel')
                self._add_tag(tag_name, n['DI_LowerLevel'], f"{n['Name']} - Нижній рівень ({n['Location']})")
            
            if n.get('DO_Run'):
                tag_name = self._create_tag_name('Noria', idx, 'DO_Run')
                self._add_tag(tag_name, n['DO_Run'], f"{n['Name']} - Контактор пуску ({n['Location']})")
        
        # Засувки
        for g in sorted(self.gates, key=lambda x: x['TypedIdx']):
            idx = g['TypedIdx']
            
            if g.get('DI_Opened'):
                tag_name = self._create_tag_name('Gate', idx, 'DI_Opened')
                self._add_tag(tag_name, g['DI_Opened'], f"{g['Name']} - Відкрита ({g['Location']})")
            
            if g.get('DI_Closed'):
                tag_name = self._create_tag_name('Gate', idx, 'DI_Closed')
                self._add_tag(tag_name, g['DI_Closed'], f"{g['Name']} - Закрита ({g['Location']})")
            
            if g.get('DO_Open'):
                tag_name = self._create_tag_name('Gate', idx, 'DO_Open')
                self._add_tag(tag_name, g['DO_Open'], f"{g['Name']} - Відкрити ({g['Location']})")
            
            if g.get('DO_Close'):
                tag_name = self._create_tag_name('Gate', idx, 'DO_Close')
                self._add_tag(tag_name, g['DO_Close'], f"{g['Name']} - Закрити ({g['Location']})")
        
        # Вентилятори
        for f in sorted(self.fans, key=lambda x: x['TypedIdx']):
            idx = f['TypedIdx']
            
            if f.get('DI_Breaker'):
                tag_name = self._create_tag_name('Fan', idx, 'DI_Breaker')
                self._add_tag(tag_name, f['DI_Breaker'], f"{f['Name']} - Автомат захисту ({f['Location']})")
            
            if f.get('DO_Run'):
                tag_name = self._create_tag_name('Fan', idx, 'DO_Run')
                self._add_tag(tag_name, f['DO_Run'], f"{f['Name']} - Пуск ({f['Location']})")
        
        print(f"✅ Створено {len(self.tags)} тегів для таблиці PLC Tags")
    
    def generate_plc_tags_excel(self) -> pd.DataFrame:
        """Генерація Excel файлу з таблицею тегів (формат TIA Portal)"""
        df_tags = pd.DataFrame(self.tags)
        
        # Другий аркуш - властивості таблиці
        df_props = pd.DataFrame([{
            'Path': 'IO_tags',
            'BelongsToUnit': '',
            'Accessibility': ''
        }])
        
        return df_tags, df_props
    
    def generate_db_mechs(self) -> str:
        """Генерація DB_Mechs.scl (БЕЗ ЗМІН)"""
        max_redlers = max([r['TypedIdx'] for r in self.redlers], default=-1) + 1 if self.redlers else 0
        max_norias = max([n['TypedIdx'] for n in self.norias], default=-1) + 1 if self.norias else 0
        max_gates = max([g['TypedIdx'] for g in self.gates], default=-1) + 1 if self.gates else 0
        max_fans = max([f['TypedIdx'] for f in self.fans], default=-1) + 1 if self.fans else 0
        
        code = self._get_header("DB_Mechs - Масиви механізмів")
        code += '''
DATA_BLOCK "DB_Mechs"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

VAR
    // ===================================================================
    // Базова шина механізмів (усі слоти 0..255)
    // ===================================================================
    Mechs : ARRAY [0..255] OF "UDT_BaseMechanism";
    
'''
        
        if max_redlers > 0:
            code += f'''    // Редлери: {len(self.redlers)} шт, масив [0..{max_redlers-1}]
    Redler : ARRAY [0..{max_redlers-1}] OF "UDT_Redler";
    
'''
        
        if max_norias > 0:
            code += f'''    // Норії: {len(self.norias)} шт, масив [0..{max_norias-1}]
    Noria : ARRAY [0..{max_norias-1}] OF "UDT_Noria";
    
'''
        
        if max_gates > 0:
            code += f'''    // Засувки: {len(self.gates)} шт, масив [0..{max_gates-1}]
    Gate : ARRAY [0..{max_gates-1}] OF "UDT_Gate2P";
    
'''
        
        if max_fans > 0:
            code += f'''    // Вентилятори: {len(self.fans)} шт, масив [0..{max_fans-1}]
    Fan : ARRAY [0..{max_fans-1}] OF "UDT_Fan";
    
'''
        
        code += '''END_VAR

BEGIN
END_DATA_BLOCK
'''
        return code
    
    def generate_fc_init_mechs(self) -> str:
        """Генерація FC_InitMechs.scl (БЕЗ ЗМІН)"""
        code = self._get_header("FC_InitMechs - Ініціалізація мапінгу")
        code += '''
FUNCTION "FC_InitMechs" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

VAR_TEMP
    i : INT;
END_VAR

BEGIN
    FOR i := 0 TO 255 DO
        "DB_Mechs".Mechs[i].DeviceType := "DB_Const".TYPE_NONE;
        "DB_Mechs".Mechs[i].TypedIndex := UINT#16#FFFF;
    END_FOR;
    
'''
        
        if self.redlers:
            code += "    // === REDLERS ===\n"
            for r in self.redlers:
                code += f'    "DB_Mechs".Mechs[{r["Slot"]}].DeviceType := "DB_Const".TYPE_REDLER;\n'
                code += f'    "DB_Mechs".Mechs[{r["Slot"]}].TypedIndex := {r["TypedIdx"]};\n\n'
        
        if self.norias:
            code += "    // === NORIAS ===\n"
            for n in self.norias:
                code += f'    "DB_Mechs".Mechs[{n["Slot"]}].DeviceType := "DB_Const".TYPE_NORIA;\n'
                code += f'    "DB_Mechs".Mechs[{n["Slot"]}].TypedIndex := {n["TypedIdx"]};\n\n'
        
        if self.gates:
            code += "    // === GATES ===\n"
            for g in self.gates:
                code += f'    "DB_Mechs".Mechs[{g["Slot"]}].DeviceType := "DB_Const".TYPE_GATE2P;\n'
                code += f'    "DB_Mechs".Mechs[{g["Slot"]}].TypedIndex := {g["TypedIdx"]};\n\n'
        
        if self.fans:
            code += "    // === FANS ===\n"
            for f in self.fans:
                code += f'    "DB_Mechs".Mechs[{f["Slot"]}].DeviceType := "DB_Const".TYPE_FAN;\n'
                code += f'    "DB_Mechs".Mechs[{f["Slot"]}].TypedIndex := {f["TypedIdx"]};\n\n'
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_fc_device_runner(self) -> str:
        """Генерація FC_DeviceRunner.scl (БЕЗ ЗМІН)"""
        code = self._get_header("FC_DeviceRunner - Виконання механізмів")
        code += '''
FUNCTION "FC_DeviceRunner" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

VAR_IN_OUT
    Mechs  : ARRAY[*] OF "UDT_BaseMechanism";
'''
        
        if self.redlers:
            code += '    Redler : ARRAY[*] OF "UDT_Redler";\n'
        if self.norias:
            code += '    Noria  : ARRAY[*] OF "UDT_Noria";\n'
        if self.gates:
            code += '    Gate   : ARRAY[*] OF "UDT_Gate2P";\n'
        if self.fans:
            code += '    Fan    : ARRAY[*] OF "UDT_Fan";\n'
        
        code += '''END_VAR

VAR_TEMP
    slot : INT;
    idx  : INT;
END_VAR

BEGIN
'''
        
        if self.redlers:
            min_slot = min([r['Slot'] for r in self.redlers])
            max_slot = max([r['Slot'] for r in self.redlers])
            code += f'''    // === REDLERS (slot {min_slot}..{max_slot}) ===
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_REDLER THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Redler"(R := Redler[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        if self.norias:
            min_slot = min([n['Slot'] for n in self.norias])
            max_slot = max([n['Slot'] for n in self.norias])
            code += f'''    // === NORIAS (slot {min_slot}..{max_slot}) ===
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_NORIA THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Noria"(N := Noria[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        if self.gates:
            min_slot = min([g['Slot'] for g in self.gates])
            max_slot = max([g['Slot'] for g in self.gates])
            code += f'''    // === GATES (slot {min_slot}..{max_slot}) ===
    FOR slot := {min_slot} TO {max_slot} DO
        IF Mechs[slot].DeviceType = "DB_Const".TYPE_GATE2P THEN
            idx := Mechs[slot].TypedIndex;
            "FC_Gate2P"(G := Gate[idx], B := Mechs[slot]);
        END_IF;
    END_FOR;
    
'''
        
        if self.fans:
            min_slot = min([f['Slot'] for f in self.fans])
            max_slot = max([f['Slot'] for f in self.fans])
            code += f'''    // === FANS (slot {min_slot}..{max_slot}) ===
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
    
    def generate_fc_hal_read(self) -> str:
        """Генерація FC_HAL_Read.scl - з СИМВОЛЬНИМИ ІМЕНАМИ"""
        code = self._get_header("FC_HAL_Read - Читання HAL входів через символьні імена")
        code += '''
FUNCTION "FC_HAL_Read" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

VAR_IN_OUT
'''
        
        if self.redlers:
            code += '    Redler : ARRAY[*] OF "UDT_Redler";\n'
        if self.norias:
            code += '    Noria  : ARRAY[*] OF "UDT_Noria";\n'
        if self.gates:
            code += '    Gate   : ARRAY[*] OF "UDT_Gate2P";\n'
        if self.fans:
            code += '    Fan    : ARRAY[*] OF "UDT_Fan";\n'
        
        code += '''END_VAR

BEGIN
'''
        
        # === REDLERS ===
        if self.redlers:
            code += '    // ===================================================================\n'
            code += '    // REDLERS\n'
            code += '    // ===================================================================\n'
            
            for r in sorted(self.redlers, key=lambda x: x['TypedIdx']):
                idx = r['TypedIdx']
                code += f'    // {r["Name"]} (Slot {r["Slot"]}, {r["Location"]})\n'
                
                if r.get('DI_Speed'):
                    tag_name = self._create_tag_name('Redler', idx, 'DI_Speed')
                    code += f'    Redler[{idx}].DI_Speed_OK    := "{tag_name}";\n'
                
                if r.get('DI_Breaker'):
                    tag_name = self._create_tag_name('Redler', idx, 'DI_Breaker')
                    code += f'    Redler[{idx}].DI_Breaker_OK  := "{tag_name}";\n'
                
                if r.get('DI_Overflow'):
                    tag_name = self._create_tag_name('Redler', idx, 'DI_Overflow')
                    code += f'    Redler[{idx}].DI_Overflow_OK := "{tag_name}";\n'
                
                code += '\n'
        
        # === NORIAS ===
        if self.norias:
            code += '    // ===================================================================\n'
            code += '    // NORIAS\n'
            code += '    // ===================================================================\n'
            
            for n in sorted(self.norias, key=lambda x: x['TypedIdx']):
                idx = n['TypedIdx']
                code += f'    // {n["Name"]} (Slot {n["Slot"]}, {n["Location"]})\n'
                
                if n.get('DI_Speed'):
                    tag_name = self._create_tag_name('Noria', idx, 'DI_Speed')
                    code += f'    Noria[{idx}].DI_Speed_OK      := "{tag_name}";\n'
                
                if n.get('DI_Breaker'):
                    tag_name = self._create_tag_name('Noria', idx, 'DI_Breaker')
                    code += f'    Noria[{idx}].DI_Breaker_OK    := "{tag_name}";\n'
                
                if n.get('DI_UpperLevel'):
                    tag_name = self._create_tag_name('Noria', idx, 'DI_UpperLevel')
                    code += f'    Noria[{idx}].DI_UpperLevel_OK := "{tag_name}";\n'
                
                if n.get('DI_LowerLevel'):
                    tag_name = self._create_tag_name('Noria', idx, 'DI_LowerLevel')
                    code += f'    Noria[{idx}].DI_LowerLevel_OK := "{tag_name}";\n'
                
                code += '\n'
        
        # === GATES ===
        if self.gates:
            code += '    // ===================================================================\n'
            code += '    // GATES\n'
            code += '    // ===================================================================\n'
            
            for g in sorted(self.gates, key=lambda x: x['TypedIdx']):
                idx = g['TypedIdx']
                code += f'    // {g["Name"]} (Slot {g["Slot"]}, {g["Location"]})\n'
                
                if g.get('DI_Opened'):
                    tag_name = self._create_tag_name('Gate', idx, 'DI_Opened')
                    code += f'    Gate[{idx}].DI_Opened_OK := "{tag_name}";\n'
                
                if g.get('DI_Closed'):
                    tag_name = self._create_tag_name('Gate', idx, 'DI_Closed')
                    code += f'    Gate[{idx}].DI_Closed_OK := "{tag_name}";\n'
                
                code += '\n'
        
        # === FANS ===
        if self.fans:
            code += '    // ===================================================================\n'
            code += '    // FANS\n'
            code += '    // ===================================================================\n'
            
            for f in sorted(self.fans, key=lambda x: x['TypedIdx']):
                idx = f['TypedIdx']
                code += f'    // {f["Name"]} (Slot {f["Slot"]}, {f["Location"]})\n'
                
                if f.get('DI_Breaker'):
                    tag_name = self._create_tag_name('Fan', idx, 'DI_Breaker')
                    code += f'    Fan[{idx}].DI_Breaker_OK := "{tag_name}";\n'
                
                code += '\n'
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_fc_hal_write(self) -> str:
        """Генерація FC_HAL_Write.scl - з СИМВОЛЬНИМИ ІМЕНАМИ"""
        code = self._get_header("FC_HAL_Write - Запис HAL виходів через символьні імена")
        code += '''
FUNCTION "FC_HAL_Write" : VOID
{ S7_Optimized_Access := 'TRUE' }
VERSION : 1.0

VAR_IN_OUT
'''
        
        if self.redlers:
            code += '    Redler : ARRAY[*] OF "UDT_Redler";\n'
        if self.norias:
            code += '    Noria  : ARRAY[*] OF "UDT_Noria";\n'
        if self.gates:
            code += '    Gate   : ARRAY[*] OF "UDT_Gate2P";\n'
        if self.fans:
            code += '    Fan    : ARRAY[*] OF "UDT_Fan";\n'
        
        code += '''END_VAR

BEGIN
'''
        
        # === REDLERS ===
        if self.redlers:
            code += '    // ===================================================================\n'
            code += '    // REDLERS\n'
            code += '    // ===================================================================\n'
            
            for r in sorted(self.redlers, key=lambda x: x['TypedIdx']):
                idx = r['TypedIdx']
                code += f'    // {r["Name"]} (Slot {r["Slot"]}, {r["Location"]})\n'
                
                if r.get('DO_Run'):
                    tag_name = self._create_tag_name('Redler', idx, 'DO_Run')
                    code += f'    "{tag_name}" := Redler[{idx}].DO_Run;\n'
                
                code += '\n'
        
        # === NORIAS ===
        if self.norias:
            code += '    // ===================================================================\n'
            code += '    // NORIAS\n'
            code += '    // ===================================================================\n'
            
            for n in sorted(self.norias, key=lambda x: x['TypedIdx']):
                idx = n['TypedIdx']
                code += f'    // {n["Name"]} (Slot {n["Slot"]}, {n["Location"]})\n'
                
                if n.get('DO_Run'):
                    tag_name = self._create_tag_name('Noria', idx, 'DO_Run')
                    code += f'    "{tag_name}" := Noria[{idx}].DO_Run;\n'
                
                code += '\n'
        
        # === GATES ===
        if self.gates:
            code += '    // ===================================================================\n'
            code += '    // GATES\n'
            code += '    // ===================================================================\n'
            
            for g in sorted(self.gates, key=lambda x: x['TypedIdx']):
                idx = g['TypedIdx']
                code += f'    // {g["Name"]} (Slot {g["Slot"]}, {g["Location"]})\n'
                
                if g.get('DO_Open'):
                    tag_name = self._create_tag_name('Gate', idx, 'DO_Open')
                    code += f'    "{tag_name}" := Gate[{idx}].DO_Open;\n'
                
                if g.get('DO_Close'):
                    tag_name = self._create_tag_name('Gate', idx, 'DO_Close')
                    code += f'    "{tag_name}" := Gate[{idx}].DO_Close;\n'
                
                code += '\n'
        
        # === FANS ===
        if self.fans:
            code += '    // ===================================================================\n'
            code += '    // FANS\n'
            code += '    // ===================================================================\n'
            
            for f in sorted(self.fans, key=lambda x: x['TypedIdx']):
                idx = f['TypedIdx']
                code += f'    // {f["Name"]} (Slot {f["Slot"]}, {f["Location"]})\n'
                
                if f.get('DO_Run'):
                    tag_name = self._create_tag_name('Fan', idx, 'DO_Run')
                    code += f'    "{tag_name}" := Fan[{idx}].DO_Run;\n'
                
                code += '\n'
        
        code += '''END_FUNCTION
'''
        return code
    
    def generate_all(self, output_dir: str = "./generated"):
        """Генерувати всі файли"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"\n📝 Генерація файлів у {output_path}...\n")
        
        # Побудувати таблицю тегів
        self.build_tags_table()
        
        files_created = []
        
        # Основні DB/FC
        self._write_file(output_path / "DB_Mechs.scl", self.generate_db_mechs(), files_created)
        self._write_file(output_path / "FC_InitMechs.scl", self.generate_fc_init_mechs(), files_created)
        self._write_file(output_path / "FC_DeviceRunner.scl", self.generate_fc_device_runner(), files_created)
        
        # HAL з символьними іменами
        self._write_file(output_path / "FC_HAL_Read.scl", self.generate_fc_hal_read(), files_created)
        self._write_file(output_path / "FC_HAL_Write.scl", self.generate_fc_hal_write(), files_created)
        
        # Таблиця тегів для TIA Portal
        df_tags, df_props = self.generate_plc_tags_excel()
        tags_path = output_path / "PLC_Tags.xlsx"
        with pd.ExcelWriter(tags_path, engine='openpyxl') as writer:
            df_tags.to_excel(writer, sheet_name='PLC Tags', index=False)
            df_props.to_excel(writer, sheet_name='TagTable Properties', index=False)
        files_created.append("PLC_Tags.xlsx")
        
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
        print("\n📋 Інструкція:")
        print("1. Імпортуйте PLC_Tags.xlsx в TIA Portal (PLC Tags)")
        print("2. Скопіюйте SCL файли в проект")
        print("3. Додайте виклики у OB1:")
        print("   - FC_HAL_Read")
        print("   - FC_DeviceRunner")
        print("   - FC_HAL_Write")
        
    except FileNotFoundError as e:
        print(f"\n❌ Помилка: файл 'elevator_config.xlsx' не знайдено")
        
    except ValueError as e:
        print(f"\n❌ Помилка валідації: {e}")
        
    except Exception as e:
        print(f"\n❌ Несподівана помилка: {e}")
        import traceback
        traceback.print_exc()
