# Commission Tax Calc – provize pro daňové přiznání

**[English ↑](README.md)**

Desktopová aplikace, která přečte provizní sestavy finančního poradce FinTrust
stažené jako PDF, sečte je za daňový rok a spočítá údaje pro přiznání k dani
z příjmů fyzických osob: **příjmy dle § 7, paušální výdaje (30 / 40 / 60 / 80 %)
a dílčí základ daně**.

![Hlavní okno (ukázková data)](docs/screenshot_cs.png)

> Data na obrázcích jsou smyšlená, vygenerovaná skriptem
> `scripts/make_demo_statements.py`.

## Co umí

- **Vybereš složku, dostaneš čísla.** Složku se sestavami vybereš tlačítkem nebo ji do okna přetáhneš. Sestavy se čtou na pozadí, takže okno nezamrzne.
- **Rozpad podle druhu činnosti.** Tabulka „Rozdělení příjmů … dle § 7 odst. 7“ se sečte za každou kategorii zvlášť a převede na sazbu paušálu, včetně zákonného stropu.
- **Kontroly, které chytí skutečné chyby:**
  - **období bez sestavy** se vypíšou. FinTrust za období s nulovou provizí sestavu nevydá, takže jde jen o poznámku, podle které poznáš i sestavu, kterou jsi zapomněl stáhnout,
  - **duplicity** z opakovaného stažení (`x (1).pdf`) se započtou jen jednou a **rozporné duplicity** (stejné období, jiná částka) se označí jako chyba,
  - **vnitřní konzistence** každé sestavy (shrnutí vs. tabulky vs. rozpad podle činnosti), takže změna formátu PDF neprojde bez povšimnutí,
  - **přelom roku**: sestava končící 31. 12. se vyplácí v lednu. Přiřazení k roku se dá zvolit podle *období* nebo podle *předpokládané výplaty*.
- **Pravidla jako data.** Sazby, stropy, převod druhu činnosti na sazbu a odkazy na zákon jsou ve verzovaných JSON souborech po letech. Při spuštění si aplikace může stáhnout novější pravidla z tohoto repozitáře. Dialog „Pravidla“ ukáže, co je načtené, a otevře aktuální znění zákona online.
- **Čeština / angličtina**, přepínatelné za běhu.
- **Příkazová řádka** se stejným jádrem: `commission-tax-calc-cli <složka> --year 2025 [--json]`.

![Dialog pravidel](docs/rules_dialog_cs.png)

## Instalace a spuštění

**Windows:** stáhni `CommissionTaxCalc.exe` z [Releases](https://github.com/konvaa/commission_tax_calc/releases) a spusť ho.

**Ze zdrojáků (Python 3.10+):**

```bash
git clone https://github.com/konvaa/commission_tax_calc.git
cd commission_tax_calc
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
commission-tax-calc
```

## Jak se aktualizují pravidla paušálů

1. Uprav `src/commission_tax_calc/rules/<rok>.json` (nebo zkopíruj loňský).
2. Zvyš `revision` a stejné číslo zapiš do `rules/index.json`.
3. Commitni a pushni do `main`. Nainstalované aplikace si změnu stáhnou při příští kontrole.

## Soukromí

- Sestavy se čtou jen lokálně a nic se neodesílá.
- Jediný síťový požadavek je volitelné stažení pravidel z `raw.githubusercontent.com`.
- `.gitignore` vylučuje všechna PDF. **Reálné sestavy nikdy necommituj**, protože obsahují jména klientů a čísla smluv.

## Upozornění

Jde o informativní výpočet, ne o daňové poradenství. Sazby a přiřazení příjmů
k roku si ověř v aktuálním znění zákona nebo u daňového poradce.

Architektura, návrhová rozhodnutí a vývoj jsou popsané v [anglickém README](README.md#how-it-works).

## Licence

[MIT](LICENSE) © 2026 Libor Konvičný
