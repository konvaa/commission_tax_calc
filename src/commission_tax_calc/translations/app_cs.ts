<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="cs_CZ">
<context>
    <name>Issues</name>
    <message>
        <location filename="../gui/issue_texts.py" line="18"/>
        <source>Could not read the statement: {reason}</source>
        <translation>Sestavu se nepodařilo přečíst: {reason}</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="21"/>
        <source>&apos;Provize celkem&apos; ({total}) does not equal regular + extraordinary ({expected}).</source>
        <translation>„Provize celkem“ ({total}) neodpovídá součtu běžných a mimořádných provizí ({expected}).</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="25"/>
        <source>&apos;Provize za běžné období&apos; ({regular}) does not match the detail tables ({expected}).</source>
        <translation>„Provize za běžné období“ ({regular}) neodpovídá součtu tabulek v sestavě ({expected}).</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="29"/>
        <source>Extraordinary commissions in the summary ({summary}) and in the table ({table}) differ.</source>
        <translation>Mimořádné provize ve shrnutí ({summary}) a v tabulce ({table}) se liší.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="33"/>
        <source>Income split by activity ({activities}) does not equal &apos;Provize celkem&apos; ({total}).</source>
        <translation>Rozdělení příjmů podle druhu činnosti ({activities}) neodpovídá „Provize celkem“ ({total}).</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="37"/>
        <source>Payout ({payout}) differs from the expected value ({expected}); this does not affect the tax base.</source>
        <translation>Částka k výplatě ({payout}) se liší od očekávané ({expected}); na základ daně to nemá vliv.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="42"/>
        <source>Duplicate of {original} (same period) - counted only once.</source>
        <translation>Duplikát souboru {original} (stejné období) – započteno jen jednou.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="45"/>
        <source>Same period as {original}, but with a different amount ({amount} vs {original_amount}). Only {original} is counted - remove the wrong file.</source>
        <translation>Stejné období jako {original}, ale jiná částka ({amount} vs {original_amount}). Započten je jen {original} – chybný soubor odstraň.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="50"/>
        <source>Period overlaps with {other}.</source>
        <translation>Období se překrývá se sestavou {other}.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="51"/>
        <source>No statement for {start} – {end}; counted as zero commission.</source>
        <translation>Za období {start} – {end} není sestava – počítá se s nulovou provizí.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="54"/>
        <source>Loaded statements for {year} only cover {first} – {last}.</source>
        <translation>Načtené sestavy pro rok {year} pokrývají jen {first} – {last}.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="57"/>
        <source>Period ends on 31 December, so it is paid out in January {next_year}. Counted in {year} (mode: {mode}).</source>
        <translation>Období končí 31. prosince, výplata tedy přijde v lednu {next_year}. Započteno do roku {year} (přiřazení: {mode}).</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="62"/>
        <source>Statements belong to more than one person: {holders}.</source>
        <translation>Sestavy patří více osobám: {holders}.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="65"/>
        <source>Unknown activity type &apos;{category}&apos; ({amount}) - choose its flat-rate percentage.</source>
        <translation>Neznámý druh činnosti „{category}“ ({amount}) – zvol sazbu paušálu.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="69"/>
        <source>No flat-rate rules for {year}; using rules for {used_year}. Check for an update.</source>
        <translation>Pro rok {year} nejsou pravidla paušálů, používají se pravidla roku {used_year}. Zkontroluj aktualizace.</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="78"/>
        <source>by payout</source>
        <translation>podle výplaty</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="79"/>
        <source>by period</source>
        <translation>podle období</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="98"/>
        <source>Info</source>
        <translation>Info</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="99"/>
        <source>Warning</source>
        <translation>Varování</translation>
    </message>
    <message>
        <location filename="../gui/issue_texts.py" line="100"/>
        <source>Error</source>
        <translation>Chyba</translation>
    </message>
</context>
<context>
    <name>MainWindow</name>
    <message>
        <location filename="../gui/main_window.py" line="268"/>
        <source>Commission Tax Calc</source>
        <translation>Provize pro daňové přiznání</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="269"/>
        <source>Open folder…</source>
        <translation>Otevřít složku…</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="270"/>
        <source>Choose the folder with downloaded statements (Ctrl+O)</source>
        <translation>Vyber složku se staženými provizními sestavami (Ctrl+O)</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="271"/>
        <source>Reload</source>
        <translation>Načíst znovu</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="272"/>
        <source>Rules…</source>
        <translation>Pravidla…</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="273"/>
        <source>Show flat-rate expense rules and their sources</source>
        <translation>Zobrazit pravidla paušálních výdajů a jejich zdroje</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="274"/>
        <source>Tax year:</source>
        <translation>Daňový rok:</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="275"/>
        <source>Assign by:</source>
        <translation>Přiřadit podle:</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="276"/>
        <source>statement period</source>
        <translation>období sestavy</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="277"/>
        <source>expected payout (cash basis)</source>
        <translation>předpokládané výplaty (příjem při úhradě)</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="280"/>
        <source>Statements contain only the period, not the payout date.
&apos;Expected payout&apos; moves a statement ending on 31 December to the next year,
because it is paid out in January. Check with your accountant which applies.</source>
        <translation>Sestavy obsahují jen období, ne datum výplaty.
„Předpokládaná výplata“ přesune sestavu končící 31. prosince do dalšího roku,
protože se vyplácí v lednu. Který způsob platí pro tebe, ověř s účetní.</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="285"/>
        <source>Commission total (Provize celkem):</source>
        <translation>Provize celkem:</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="286"/>
        <source>Income § 7:</source>
        <translation>Příjmy dle § 7:</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="287"/>
        <source>Flat-rate expenses:</source>
        <translation>Paušální výdaje:</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="288"/>
        <source>Partial tax base § 7:</source>
        <translation>Dílčí základ daně § 7:</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="289"/>
        <source>Tax return summary</source>
        <translation>Souhrn pro daňové přiznání</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="292"/>
        <source>Informative calculation, not tax advice. Verify the rates against the current law (Rules… → Open current law online) or with a tax advisor.</source>
        <translation>Informativní výpočet, nejde o daňové poradenství. Sazby ověř v aktuálním znění zákona (Pravidla… → Otevřít aktuální znění online) nebo u daňového poradce.</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="297"/>
        <source>Severity</source>
        <translation>Závažnost</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="297"/>
        <source>Statement</source>
        <translation>Sestava</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="297"/>
        <source>Message</source>
        <translation>Zpráva</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="299"/>
        <source>Show informational notes</source>
        <translation>Zobrazit informativní poznámky</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="312"/>
        <source>Folder with statements</source>
        <translation>Složka s provizními sestavami</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="347"/>
        <source>Reading {0} ({1}/{2})</source>
        <translation>Čtu {0} ({1}/{2})</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="354"/>
        <source>Read {0} statement(s), {1} failed.</source>
        <translation>Načteno sestav: {0}, chyb: {1}.</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="417"/>
        <source>Unknown activity type</source>
        <translation>Neznámý druh činnosti</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="419"/>
        <source>The statements contain an activity type the rules do not know:

„{0}“ ({1})

Which flat-rate category does it belong to?</source>
        <translation>Sestavy obsahují druh činnosti, který pravidla neznají:

„{0}“ ({1})

Do které kategorie paušálních výdajů patří?</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="441"/>
        <source>No folder selected – click “Open folder…” or drop a folder here.</source>
        <translation>Není vybraná složka – klikni na „Otevřít složku…“ nebo sem složku přetáhni.</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="444"/>
        <source>Folder: {0}</source>
        <translation>Složka: {0}</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="448"/>
        <source>Statements ({0} counted of {1})</source>
        <translation>Provizní sestavy (započteno {0} z {1})</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="463"/>
        <source>bundled</source>
        <translation>přibalená</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="463"/>
        <source>downloaded</source>
        <translation>stažená</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="464"/>
        <source>Rules {0}, revision {1} ({2})</source>
        <translation>Pravidla {0}, revize {1} ({2})</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="471"/>
        <source>Rules: —</source>
        <translation>Pravidla: —</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="515"/>
        <source>Findings ({0} to check)</source>
        <translation>Upozornění (ke kontrole: {0})</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="550"/>
        <location filename="../gui/main_window.py" line="597"/>
        <location filename="../gui/main_window.py" line="606"/>
        <source>Flat-rate expense rules</source>
        <translation>Pravidla paušálních výdajů</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="551"/>
        <source>Check online for updated flat-rate expense rules?</source>
        <translation>Zkontrolovat online aktualizaci pravidel paušálních výdajů?</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="554"/>
        <source>The app downloads a small rules file from the project&apos;s GitHub repository. No personal data is sent.</source>
        <translation>Aplikace stáhne malý soubor s pravidly z GitHub repozitáře projektu. Žádná osobní data se neodesílají.</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="559"/>
        <source>Remember my choice</source>
        <translation>Zapamatovat volbu</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="576"/>
        <source>Checking for rule updates…</source>
        <translation>Kontroluji aktualizace pravidel…</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="592"/>
        <source>Rules updated for: {0}</source>
        <translation>Pravidla aktualizována pro: {0}</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="594"/>
        <source>Rules are up to date.</source>
        <translation>Pravidla jsou aktuální.</translation>
    </message>
    <message>
        <location filename="../gui/main_window.py" line="603"/>
        <source>Could not update rules, using the saved ones. ({0})</source>
        <translation>Pravidla se nepodařilo aktualizovat, používám uložená. ({0})</translation>
    </message>
</context>
<context>
    <name>RulesDialog</name>
    <message>
        <location filename="../gui/rules_dialog.py" line="156"/>
        <source>Flat-rate expense rules</source>
        <translation>Pravidla paušálních výdajů</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="157"/>
        <source>Tax year:</source>
        <translation>Daňový rok:</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="158"/>
        <source>Rates (§ 7 odst. 7 ZDP)</source>
        <translation>Sazby (§ 7 odst. 7 ZDP)</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="159"/>
        <source>How statement activity types map to rates</source>
        <translation>Jak se druhy činnosti ze sestav převádějí na sazby</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="160"/>
        <source>Your manual choices</source>
        <translation>Tvoje ruční volby</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="161"/>
        <source>Sources</source>
        <translation>Zdroje</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="162"/>
        <source>Open current law online</source>
        <translation>Otevřít aktuální znění online</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="163"/>
        <source>Check for updates now</source>
        <translation>Zkontrolovat aktualizace</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="164"/>
        <source>Clear manual choices</source>
        <translation>Smazat ruční volby</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="165"/>
        <source>Check for rule updates at startup:</source>
        <translation>Kontrola aktualizací pravidel při spuštění:</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="166"/>
        <source>Ask</source>
        <translation>Zeptat se</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="166"/>
        <source>Always</source>
        <translation>Vždy</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="166"/>
        <source>Never</source>
        <translation>Nikdy</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="170"/>
        <location filename="../gui/rules_dialog.py" line="177"/>
        <location filename="../gui/rules_dialog.py" line="178"/>
        <source>Rate</source>
        <translation>Sazba</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="171"/>
        <source>Max. expenses</source>
        <translation>Max. výdaje</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="172"/>
        <source>Category</source>
        <translation>Kategorie</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="173"/>
        <source>Provision</source>
        <translation>Ustanovení</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="174"/>
        <source>Examples</source>
        <translation>Příklady</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="177"/>
        <source>Statement text contains</source>
        <translation>Text v sestavě obsahuje</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="178"/>
        <source>Activity type</source>
        <translation>Druh činnosti</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="186"/>
        <source>No rules available.</source>
        <translation>Žádná pravidla nejsou k dispozici.</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="189"/>
        <source>bundled with the app</source>
        <translation>přibalená v aplikaci</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="189"/>
        <source>downloaded</source>
        <translation>stažená</translation>
    </message>
    <message>
        <location filename="../gui/rules_dialog.py" line="191"/>
        <source>Revision {0}, updated {1}, source: {2}. Income cap per rate: {3}.</source>
        <translation>Revize {0}, aktualizováno {1}, zdroj: {2}. Strop příjmů pro každou sazbu: {3}.</translation>
    </message>
</context>
<context>
    <name>StatementsModel</name>
    <message>
        <location filename="../gui/table_models.py" line="107"/>
        <source>File</source>
        <translation>Soubor</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="108"/>
        <source>Period</source>
        <translation>Období</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="109"/>
        <source>Tax year</source>
        <translation>Daňový rok</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="110"/>
        <source>Commission total</source>
        <translation>Provize celkem</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="111"/>
        <source>Payout</source>
        <translation>K výplatě</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="112"/>
        <source>Status</source>
        <translation>Stav</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="159"/>
        <source>Not read</source>
        <translation>Nenačteno</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="161"/>
        <source>Not counted</source>
        <translation>Nezapočteno</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="163"/>
        <source>OK</source>
        <translation>OK</translation>
    </message>
</context>
<context>
    <name>TaxModel</name>
    <message>
        <location filename="../gui/table_models.py" line="216"/>
        <source>Rate</source>
        <translation>Sazba</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="217"/>
        <source>Category</source>
        <translation>Kategorie</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="218"/>
        <source>Income</source>
        <translation>Příjmy</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="219"/>
        <source>Expenses</source>
        <translation>Výdaje</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="220"/>
        <source>Partial tax base</source>
        <translation>Dílčí základ daně</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="237"/>
        <source>Unknown activity type - choose a rate in the dialog.</source>
        <translation>Neznámý druh činnosti – zvol sazbu v dialogu.</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="239"/>
        <source>Activities in statements:</source>
        <translation>Druhy činnosti v sestavách:</translation>
    </message>
    <message>
        <location filename="../gui/table_models.py" line="241"/>
        <source>Income exceeds the cap; expenses are limited.</source>
        <translation>Příjmy překračují strop, výdaje jsou omezeny.</translation>
    </message>
</context>
</TS>
