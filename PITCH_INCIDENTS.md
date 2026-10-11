# Pitch (5 minutes), dans l'ordre de la page

Le pitch suit le brief : **d'abord** montrer qu'une position dépend d'une pile de dépendances (le graphe), **ensuite**
répondre à la question du risk manager avec les incidents.
Le texte en italique est à dire. « À l'écran » dit quoi montrer. Les critères du jury sont indiqués entre crochets.

Chiffres : fork d'Ethereum au bloc 26 164 635 ; le fonds détient 1 M de PT dans chaque position.

---

## 0 · Accroche (20 s)

*« Un PT Pendle, c'est une ligne dans un portefeuille. Le brief nous demande deux choses : identifier automatiquement
ce dont cette ligne dépend, puis répondre à la question qu'un risk manager se pose vraiment : est-ce qu'on reste, ou est-ce
que la perte attendue justifie de sortir malgré le coût d'exécution ? »*

**À l'écran** : le haut de la page.

---

## 1 · Identifier les dépendances (1 min 15) [Découverte, 30 %]

*« Voici trois PT qui se ressemblent : sUSDe, reUSD et sUSDS. On donne le nom et l'échéance de chaque PT. Le programme
retrouve son adresse chez Pendle, puis construit seul cette carte à partir de cette adresse : il interroge Morpho et
DefiLlama, et lit directement les contrats sur la blockchain. Elle suit les cinq
couches du brief. Tout à gauche, ce sur quoi tout repose : Ethereum, Pendle et Morpho. Puis, de gauche à droite, l'ordre
dans lequel un incident se propage : l'émetteur qui produit le rendement, l'oracle qui transmet un choc au prix de prêt,
les marchés Morpho qui liquident, le pool où leurs PT sont déversés, et enfin nos positions. »*

*« La carte montre ce qu'une analyse token par token ne voit pas. Un même prêteur, Smokehouse USDT, finance 38 % du
marché de prêt reUSD en USDT et 83 % de celui de sUSDS en USDT : une perte sur l'un peut vider l'autre. Les trois PT reposent sur un contrat que la
gouvernance de Pendle peut mettre en pause, avec le même propriétaire. Et surtout, la même couche cache trois oracles
différents : celui de sUSDe ignore le marché, celui de reUSD le suit toutes les 15 minutes, celui de sUSDS le suit avec un
plancher. C'est ce qui va décider de la suite. »*

*(Optionnel, 20 s, en direct)* *« Et ce n'est pas écrit à la main pour ces trois-là. Prenons un PT qu'on n'a jamais
regardé. »* Dans un terminal (dossier `src`) :
```powershell
python -m defi_risk.map USD3 2026-12-17
```
*« En quatre secondes : son émetteur, 3Jane, son marché de prêt Morpho avec 31 millions de garanties, le coffre Yearn
qui prête dedans, son oracle, et ce qu'il partage avec notre book. »*


**À l'écran** : le graphe en 5 couches (une couleur par type : violet émetteur, vert d'eau oracle, orange prêt, bleu
pool ; la légende est juste en dessous) ; cliquer sur l'oracle de sUSDe (« Oracle: primary/backup ») puis sur
« Smokehouse USDT » pour montrer les 38 % / 83 % ; les 4 puces « What the three positions share » ; ouvrir une seconde le
bloc replié de l'écosystème.

---

## 2 · Rester ou sortir ? (2 min 30) [Impact, 30 % · Décision, 25 % · Démo, 15 %]

### La réponse chiffrée (30 s)

*« La question du risk manager, on la pose telle quelle, avec trois chiffres. Pour sUSDe : sortir maintenant coûte
0,22 %. On l'a mesuré en vendant vraiment un million de PT dans le pool, sur notre copie d'Ethereum. Sortir fait aussi
renoncer à 0,12 % de rendement. Rester coûte en moyenne 0,16 %, mais entre 0,07 et 0,43 % selon l'incertitude.
Au centre, rester gagne ; dans le haut de la fourchette, sortir gagne. Les données ne tranchent pas : on réduit la
position plutôt que de tout garder ou tout vendre. »*

*« Ces probabilités ne sont pas inventées : on les a mesurées sur l'historique de 17 stablecoins comparables, avec un
intervalle de confiance. »*

**À l'écran** : onglet PT-sUSDe, badge UNCLEAR orange, les trois chiffres, puis les 3 puces juste en dessous :
« Exiting: 0.22% + 0.12% = 0.34% », « Staying: 0.16% (up to 0.43%) », « → Hold less ». Les lire telles quelles.

*(Optionnel, 15 s, en direct)* *« Et pour n'importe quelles quantités, le risk manager tape son book : »* Dans un
terminal (dossier `src`) :
```powershell
python -m defi_risk.decide sUSDe=2000000 reUSD=500000 sUSDS=1000000
```
*« Un verdict par ligne, avec les mêmes trois chiffres et le temps pour agir. »*

### Les incidents, et ce qu'ils font au book (1 min 30, en direct)

*« Mais le brief insiste : remarquer un incident n'est pas le difficile. Le difficile, c'est savoir ce qu'il fait au book,
et en combien de temps. Ce tableau le dit, incident par incident. Je vais vous montrer le premier en direct. »*

**À l'écran** : le tableau « When an incident hits this position » (colonnes Effect on 1M PT, Time to act, Chance) et la
ligne « Action » en dessous (« Watch USDe/USD below 0.9925 → 16 h to exit »). Puis le panneau « Live on the local chain:
your book, right now », avec « What the market is doing » ouvert. Lancer l'incident 1 depuis la fenêtre 4, une étape à
la fois. Les couleurs racontent l'incident : tout est vert au départ, le prix d'USDe et l'écart de l'oracle passent en
rouge, l'oracle « challenged » en rouge, puis l'emprunteur liquidable en rouge, et la poche passe de `normal` (vert) à
`last moment` puis `stuck` (rouge).

1. **1a, USDe à 0,99 $** : *« USDe perd 1 %. Notre poche vaut 981 000 $ au lieu de 990 000, mais elle est encore
   vendable : l'oracle de Morpho ignore le prix d'USDe. Il faut 16 heures de contestation pour qu'il bascule. »*
2. **1b, contestation** : *« Le compte à rebours démarre : 16 heures. C'est notre fenêtre de sortie. »*
3. **1c, 16 heures plus tard** : *« L'oracle bascule. La baleine, qui était à 0,97 % de sa liquidation, devient
   liquidable. Notre poche passe en "last moment". »*
4. **1d-1e, liquidation et ventes** : *« Le liquidateur saisit 3,07 millions de PT et les revend. Le pool est plein. Notre
   poche : 900 000 PT bloqués. Le même ordre de vente, 16 heures plus tôt, passait. »*

*(Optionnel, 30 s, si le temps le permet : rejouer avec le robot, README « Incident 1 again, with the auto-exit
robot »)* *« Même incident, mais cette fois un robot surveille la poche. Il ne vend pas au premier signal : un creux
court ne le fait pas bouger. Il vend quand il reste moins de 2 heures avant que l'oracle bascule. »* Fenêtre 5 :
`sold 1,000,000 PT for about $981,041`, la poche passe en `exited` en vert. *« Le pool se remplit exactement comme
avant, mais nous sommes déjà dehors. Sans robot : 900 000 PT bloqués. Avec : 981 000 dollars. Et pour reUSD, où la
fenêtre est de 15 minutes, c'est la seule façon de sortir. »*

*« Tout ça s'exécute sur les vrais contrats : la liquidation à la main donne 3 073 266 PT, la simulation automatique
3 073 270. Les chiffres sont reproductibles. »*

### Les deux autres positions (30 s)

*« Même question, réponses différentes. reUSD : on reste, son rendement de 11,8 % couvre largement la perte attendue. Mais
une dépréciation de 1 % par l'émetteur bloque la position, et son oracle suit le marché toutes les 15 minutes : la fenêtre
de sortie est de 15 minutes. Aucun humain ne la tient, la sortie doit être automatisée. sUSDS : bloqué à partir d'un
décrochage de 2 % d'USDS, et exposé par contagion à reUSD via le prêteur commun. »*

**À l'écran** : cliquer sur l'onglet PT-reUSD (badge STAY vert, ligne Action « 15 min to exit → automate it »), puis
PT-sUSDS (UNCLEAR orange). Sur chaque onglet, le graphique « … : what the fund gets for its 1M PT » montre la falaise :
barres vertes = vendu à temps, barre rouge à 0 = bloqué (à partir de 1 % pour sUSDe et reUSD, 2 % pour sUSDS).

*(Optionnel, 20 s)* **Incident 6, la pause Pendle** : *« Dernière couche : la gouvernance de Pendle met le contrat en
pause. Aucun prix ne bouge, et pourtant la poche est bloquée instantanément. »*

---

## 3 · Le book (30 s) [Décision]

*« À l'échelle du portefeuille : il y a 8,5 % de chances qu'au moins une poche devienne invendable avant son échéance,
entre 4,4 et 14,9 % selon l'incertitude. Et la contagion fait tomber deux poches ensemble alors qu'elles n'ont aucun
émetteur en commun. Côté taille : la limite d'une position, c'est la place dans le pool en cas de crise, pas le
rendement. Le calculateur le montre. »*

**À l'écran** : la section « Which incident hits which pocket » (les 2 puces en haut, les poches touchées en rouge
« stuck ») ; puis, dans la partie 2, ouvrir « And with a different position size? » et monter la taille jusqu'à REDUCE.

---

## 4 · Clôture (20 s)

*« On identifie automatiquement les dépendances, on mesure leur impact en rejouant les incidents sur les vrais contrats,
et on répond à la question rester ou sortir, avec le délai pour agir : réduire sUSDe et sUSDS, garder reUSD avec une
sortie automatisée. Nos limites : peu d'événements historiques pour les probabilités, un comportement des liquidateurs
encadré par deux hypothèses, et une panne d'Ethereum ou un bug dans Morpho ou Pendle que nous ne simulons pas. »*

---

## Où chaque critère est couvert

| Critère | Moment du pitch | Preuve à montrer |
|---|---|---|
| Découverte (30 %) | Partie 1 | Le graphe en 5 couches, les dépendances partagées, les 3 oracles lus dans les contrats, le scan de 9 PT |
| Impact défendable (30 %) | Partie 2, incidents | Exécution réelle des contrats, chiffres identiques à la main et en automatique, fourchettes de probabilité |
| Décision (25 %) | Partie 2, réponse chiffrée, et partie 3 | Coût d'exécution vs perte attendue, verdict en couleur avec fourchette, temps pour agir, taille maximale, `decide` pour n'importe quelles quantités |
| Démo sur données réelles (15 %) | Partie 2, en direct | Fork du vrai Ethereum, vrais emprunteurs et pools ; seuls des flux de prix sont remplacés |

## Si le direct plante
Tout est déjà sur la page : le tableau des incidents et le graphique « USDe depeg: what the fund gets for its 1M PT »
montrent les mêmes chiffres que l'incident en direct (barre verte à 981k à 1 %, barre rouge à 0). Continue dessus sans
t'arrêter.

## Questions probables, réponses courtes
- **« Pourquoi UNCLEAR et pas un verdict net ? »** Parce que la fourchette de probabilité traverse le point d'équilibre.
  Forcer un verdict serait inventer de la précision. On recommande de réduire.
- **« D'où viennent les probabilités ? »** Taux observé de décrochages durables sur 17 stablecoins comparables, avec un
  intervalle de Poisson à 90 %. Peu d'événements, donc une fourchette large, et nous le disons.
- **« Le slippage est-il compté ? »** Oui : le coût d'exécution est mesuré par une vraie vente sur le pool. Il n'inclut pas
  la conversion de l'actif en dollars après la vente.
- **« Et si on détient d'autres quantités ? »** `python -m defi_risk.decide` donne le verdict pour n'importe quelles
  quantités des 3 PT. Limite à dire : la perte attendue est celle mesurée pour 1 M de PT, seuls le coût de sortie et la
  capacité du pool changent avec la taille.
- **« Ça marche pour n'importe quel token ? »** La découverte, oui (9 PT scannés). La simulation est écrite pour ces
  3 tokens, choisis pour couvrir 3 conceptions d'oracle différentes.
