# 5-rindu Tic-Tac-Toe (ar Swap2) — Tehniskā specifikācija

## 1. Spēles pamatnoteikumi
* **Laukums:** Kvadrātveida režģis `15 x 15` (indeksi `0` līdz `14`).
* **Simboli:**
  * `"_"` — tukša rūtiņa
  * `"X"` — 1. spēlētājs (melnie)
  * `"O"` — 2. spēlētājs (baltie)
* **Uzvara:** Spēlētājs uzvar, ja pēc viņa gājiena uz laukuma izveidojas vismaz **5 vienādi simboli pēc kārtas** horizontāli, vertikāli vai pa diagonāli.
* **Neizšķirts:** Ja visas `225` rūtiņas ir aizpildītas un nevienam nav 5 pēc kārtas.

---

## 2. Swap2 atklātnes noteikumi
1. **1. spēlētājs** uz tukša laukuma novieto **3 figūras**: divas `"X"` un vienu `"O"`.
2. **2. spēlētājs** izvēlas vienu no trim darbībām:
   * **`TAKE_O`** — 2. spēlētājs spēlē ar `"O"`, 1. spēlētājs spēlē ar `"X"`. Nākamo (4.) gājienu veic `"O"`.
   * **`TAKE_X`** — 2. spēlētājs spēlē ar `"X"`, 1. spēlētājs spēlē ar `"O"`. Nākamo (4.) gājienu veic `"O"`.
   * **`PLACE_TWO`** — 2. spēlētājs novieto uz brīvām rūtiņām vēl vienu `"X"` un vienu `"O"`, un krāsas izvēli nodod 1. spēlētājam.
3. **1. spēlētājs** (tikai pēc `PLACE_TWO`) izvēlas spēlēt ar `"X"` vai `"O"`. Spēle turpinās ar secīgiem gājieniem.

---

## 3. Faila struktūra un prasības
Katrs dalībnieks iesniedz vienu Python moduli ar spēles funkcijām:
`studenti/vards_uzvards/bot.py`
Cits modulis apstrādā grafisko interfeisu un importē šo moduli.
Funkcijas ir nodalītas, lai boti varētu sacensties savā starpā.

### Ierobežojumi
* Modulis nedrīkst saturēt `input()` izsaukumus.
* Importējot moduli, nedrīkst automātiski palaisties spēles cikls vai GUI (visam palaišanas kodam jāatrodas zem `if __name__ == "__main__":`).
* Kods nedrīkst modificēt ieejas sarakstu `board` pa tiešo (vai arī pirms izmaiņām jāveic kopēšana).
* Maksimālais izpildes laiks vienam gājienam: `1.0` sekunde.

---

## 4. Obligātās konstantes un funkcijas (`bot.py`)

### `BOT_NAME`
* **Definīcija:** `BOT_NAME: str = "Dalībnieka vai bota nosaukums"`
* **Apraksts:** Identifikācijas virkne, kas tiek attēlota turnīra kopvērtējuma tabulā un spēļu žurnālā.

---

### `get_move(board, player)`
* **Vispārīgais apraksts:** Galvenā spēles lēmumu pieņemšanas funkcija. Turnīra dzinējs vai grafiskais interfeiss to izsauc katrā kārtējā gājienā pēc atklātnes fāzes, lai noskaidrotu, kurā brīvajā laukuma rūtiņā bots vēlas novietot savu nākamo figūru.
* **Ieeja:**
  * `board: list[list[str]]` — `15 x 15` divdimensiju saraksts ar `"_"`, `"X"`, `"O"`.
  * `player: str` — simbols (`"X"` vai `"O"`), ar kuru dotajā partijā spēlē šis bots.
* **Izeja:**
  * `tuple[int, int]` — izvēlētās brīvās rūtiņas koordinātas `(rinda, kolonna)`, kur `0 <= rinda <= 14` un `0 <= kolonna <= 14`.

---

### `swap2_propose(board)`
* **Vispārīgais apraksts:** Atklātnes sākuma funkcija, ko izsauc tikai tad, ja bots partiju sāk kā 1. spēlētājs. Funkcijas uzdevums ir uz tukša laukuma izveidot sākotnējo trīs figūru pozīciju pirms krāsu sadales.
* **Ieeja:**
  * `board: list[list[str]]` — tukšs `15 x 15` laukums.
* **Izeja:**
  * `list[tuple[int, int, str]]` — saraksts ar precīzi 3 elementiem `(rinda, kolonna, simbols)`: divi ar `"X"` un viens ar `"O"` savstarpēji atšķirīgās koordinātās.

---

### `swap2_respond(board)`
* **Vispārīgais apraksts:** Atklātnes atbildes funkcija, ko izsauc tikai tad, ja bots ir 2. spēlētājs un pretinieks tikko ir novietojis pirmās trīs figūras. Funkcija novērtē izveidoto sākuma pozīciju un izlemj, vai uzreiz pārņemt kādu no krāsām (`TAKE_X` / `TAKE_O`), vai arī papildināt laukumu ar vēl divām figūrām (`PLACE_TWO`), nododot krāsas izvēli atpakaļ pretiniekam.
* **Ieeja:**
  * `board: list[list[str]]` — `15 x 15` laukums ar 3 aizņemtām rūtiņām.
* **Izeja (`dict`):** Viens no šiem trim vārdnīcas formātiem:
  * `{"action": "TAKE_X"}`
  * `{"action": "TAKE_O"}`
  * `{"action": "PLACE_TWO", "moves": [(r1, c1, "X"), (r2, c2, "O")]}` (abas koordinātas brīvas un savstarpēji atšķirīgas)

---

### `swap2_final_choice(board)`
* **Vispārīgais apraksts:** Noslēdzošā atklātnes funkcija, ko izsauc 1. spēlētājam tikai gadījumā, ja 2. spēlētājs iepriekšējā solī izvēlējās `PLACE_TWO`. Funkcija apskata laukumu ar piecām figūrām un nosaka, ar kuru simbolu bots turpinās pamatspēli.
* **Ieeja:**
  * `board: list[list[str]]` — `15 x 15` laukums ar 5 aizņemtām rūtiņām.
* **Izeja:**
  * `str` — izvēlētais simbols (`"X"` vai `"O"`).

---

## 5. Grafiskā interfeisa (GUI) saderība
* GUI skriptam (piemēram, `gui.py` tajā pašā mapē) ir jāimportē `get_move` un Swap2 funkcijas no sava `bot.py` (`from bot import get_move, swap2_propose, swap2_respond, swap2_final_choice`).
* Spēles loģika un AI lēmumu pieņemšana nedrīkst būt ielikta GUI pogu apstrādātājos — GUI tikai nolasa laukuma stāvokli, padod to `bot.py` funkcijām un attēlo atgrieztās koordinātas.

## 6. Spēles palaišana
* Grafisko cilvēka un bota spēli palaiž ar `python gui.py` no projekta mapes.
* Pirms spēles var izvēlēties botu un to, kurš sāk. `Swap2` ļauj otrajam spēlētājam izvēlēties krāsu vai novietot vēl divas figūras, pēc kā pirmais izvēlas krāsu, mazinot pirmā gājiena priekšrocību.
* Uzvara tiek noteikta piecām vienādām figūrām pēc kārtas; ja laukums piepildās bez uzvarētāja, spēle beidzas neizšķirti.
