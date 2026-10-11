# Pitch (5 minutes), dans l'ordre de la page

D'abord le graphe des dépendances, ensuite la question du risk manager avec l'incident en direct.
Le texte en italique est à dire (environ 570 mots, soit 4 min de parole à un rythme calme ; le reste, ce sont les
clics et l'attente des commandes). « À l'écran » dit quoi montrer.

| Partie | Durée | Cumul |
|---|---|---|
| 0 · Accroche | 25 s | 0:25 |
| 1 · Dépendances | 1 min | 1:25 |
| 2 · Rester ou sortir | 40 s | 2:05 |
| 3 · L'incident en direct | 1 min 45 | 3:50 |
| 4 · Les deux autres positions et le book | 50 s | 4:40 |
| 5 · Clôture | 20 s | 5:00 |

## Avant de monter sur scène
- Anvil lancé, étape 0 faite, snapshot pris, fenêtre 3 (`forkwatch`) relancée **avant** l'incident.
- Page ouverte sur http://localhost:8765, en haut, onglet PT-sUSDe sélectionné.
- Dans « Live on the local chain », le bloc « What the market is doing » déjà ouvert.
- Fenêtre 4 prête, avec les blocs 1a, 1b, 1c, 1d+1e du README copiés à l'avance : **un collage par étape**.

---

## 0 · Accroche (25 s)

*« Une position on-chain, c'est une ligne dans un book. Mais derrière cette ligne, il y a une chaîne, un émetteur, un
oracle, un marché, des prêteurs, et on ne voit presque rien de tout ça depuis la position. Belem nous a donné un
exemple, le PT Pendle. On l'a pris sur trois actifs qui couvrent leurs autres cas : un coffre qui couvre ses positions
sur des plateformes de perp, des actifs dont le prix vient d'un seul flux, et un émetteur unique. Deux questions : de
quoi dépend la ligne, et quand un incident arrive, on reste ou on sort ? »*

**À l'écran** : le haut de la page.

## 1 · Les dépendances (1 min) [Découverte, 30 %]

*« On donne le nom et l'échéance de trois PT. Le programme construit seul cette carte en interrogeant Pendle, Morpho,
DefiLlama et les contrats eux-mêmes. À gauche, ce sur quoi tout repose : Ethereum, Pendle, Morpho. Puis le chemin d'un
incident : l'émetteur, l'oracle, les marchés de prêt qui liquident, le pool où les PT sont revendus, et nos positions. »*

*« La carte voit ce qu'une analyse token par token rate. Un même prêteur, Smokehouse, finance 38 % d'un marché reUSD et
83 % d'un marché sUSDS : une perte sur l'un peut vider l'autre. Pendle peut mettre les trois en pause d'un coup. Et la
même couche cache trois oracles différents : c'est ce qui décide de tout le reste. »*

**À l'écran** : le graphe ; cliquer sur « Smokehouse USDT » (38 % / 83 %) ; les 4 puces « What the three positions share ».

## 2 · Rester ou sortir ? (40 s) [Décision, 25 %]

*« Toute cette carte se résume en un chiffre : ce que rester rapporte de plus que sortir. Pour sUSDe, plus 0,18 %. Il
vient de trois mesures : sortir coûte 0,22 %, mesuré en vendant vraiment un million de PT dans le pool, plus 0,12 % de
rendement abandonné ; rester coûte en moyenne 0,16 %. Mais la fourchette va de moins 0,09 à plus 0,27 % : elle passe par
zéro, donc on réduit la position. Les probabilités viennent de l'historique de 17 stablecoins comparables. »*

**À l'écran** : le badge UNCLEAR orange avec « +0.18% · +$1.8k » en grand et sa fourchette ; les 3 puces en dessous.

## 3 · L'incident en direct (1 min 45) [Impact, 30 % · Démo, 15 %]

*« Le brief le dit : remarquer l'incident n'est pas le difficile. Le difficile, c'est ce qu'il fait au book, et en
combien de temps. Je le joue sur une copie d'Ethereum, avec les vrais contrats et les vrais emprunteurs. »*

**À l'écran** : le panneau « Live on the local chain ». Un collage par étape dans la fenêtre 4.

1. **1a + 1b collés ensemble** : *« USDe perd 1 %. Notre poche vaut encore 981 000 dollars et reste vendable : l'oracle
   ignore USDe tant qu'il n'a pas été contesté 16 heures. Quelqu'un lance la contestation : on a 16 heures. »*
2. **1c** : *« 16 heures plus tard, l'oracle bascule, la baleine devient liquidable. Dernier moment pour vendre. »*
3. **1d + 1e** : *« Le liquidateur saisit 3 millions de PT et les revend. Le pool est plein : 900 000 de nos PT sont
   bloqués. »*

*« Et ce tableau dit ce qu'attendre a coûté : sortir à temps, 981 000 dollars ; avoir attendu, 98 000. 883 000 dollars
sur une seule poche. »*

**À l'écran** : la poche passe de `normal` (vert) à `last moment` puis `partly stuck` (rouge) ; finir sur le tableau
« With auto-exit: exiting in time vs waiting » (+$883k surligné en vert).

## 4 · Les deux autres positions et le book (50 s)

*« Même question, autres réponses. reUSD : on reste, 11,8 % de rendement couvrent le risque, mais son oracle suit le
marché en 15 minutes : aucun humain ne tient cette fenêtre, la sortie doit être automatique. sUSDS : on réduit. »*

*« Sur le book : 8,5 % de chances qu'au moins une poche soit bloquée avant l'échéance. Et la vraie limite de taille, c'est
la place dans le pool en cas de crise, pas le rendement. »*

**À l'écran** : onglet PT-reUSD (STAY vert, « 15 min to exit → automate it ») ; onglet PT-sUSDS ; descendre sur
« Which incident hits which pocket ».

## 5 · Clôture (20 s)

*« On trouve automatiquement les dépendances, on mesure l'impact en rejouant les incidents sur les vrais contrats, et on
répond : réduire sUSDe et sUSDS, garder reUSD avec une sortie automatique. Nos limites : peu d'historique pour les
probabilités, et un bug de Pendle ou Morpho que nous ne simulons pas. »*

---

## Coupes si tu es en retard
- Partie 4 : ne dire que la phrase reUSD, sauter le book.
- Partie 1 : sauter la phrase sur la pause Pendle.
- Partie 3 : coller 1c et 1d+1e d'un coup et ne commenter que la fin.

## Bonus, seulement si on te le demande (pas dans les 5 min)
- **Cartographier un PT jamais vu**, depuis `src` : `python -m defi_risk.map USD3 2026-12-17` (4 secondes).
- **Verdict pour n'importe quelles quantités** : `python -m defi_risk.decide sUSDe=2000000 reUSD=500000 sUSDS=1000000`.
- **Le robot de sortie** (README « Incident 1 again, with the auto-exit robot ») : il vend 1,5 h avant la bascule,
  981 000 $, la poche passe en `exited`. Un creux court ne le fait pas vendre.
- **La pause Pendle** (incident 6) : aucun prix ne bouge, la poche est bloquée instantanément.
- **Reproductibilité** : la liquidation à la main donne 3 073 266 PT, la simulation automatique 3 073 270.

## Où chaque critère est couvert

| Critère | Moment du pitch | Preuve à montrer |
|---|---|---|
| Découverte (30 %) | Partie 1 | Le graphe en 5 couches, le prêteur commun, les 3 oracles lus dans les contrats |
| Impact défendable (30 %) | Partie 3 | Exécution réelle des contrats, +883 000 $ entre sortir à temps et attendre, fourchettes de probabilité |
| Décision (25 %) | Parties 2 et 4 | Coût d'exécution vs perte attendue, verdict avec fourchette, temps pour agir, limite de taille |
| Démo sur données réelles (15 %) | Partie 3, en direct | Fork du vrai Ethereum, vrais emprunteurs et pools ; seuls des flux de prix sont remplacés |

## Si le direct plante
Tout est déjà sur la page : le tableau des incidents et le graphique « USDe depeg: what the fund gets for its 1M PT »
montrent les mêmes chiffres (barre verte à 981k à 1 %, barre rouge à 0). Continue dessus sans t'arrêter.

## Questions probables, réponses courtes
- **« Votre chiffre inclut quoi ? »** La perte de parité du stablecoin (ou la dépréciation de reUSD), probabilisée sur
  l'historique. La panne d'oracle, la panique sur le pool et la pause Pendle sont simulées mais pas probabilisées : la
  page le dit sous le chiffre. La contagion Smokehouse est laissée dehors exprès : elle bloque la sortie, mais le PT
  rembourse quand même 1 USDS à l'échéance, donc pas de perte définitive pour un fonds sans levier.
- **« Pourquoi UNCLEAR et pas un verdict net ? »** La fourchette de probabilité traverse le point d'équilibre. Forcer un
  verdict serait inventer de la précision. On recommande de réduire.
- **« D'où viennent les probabilités ? »** Taux observé de décrochages durables sur 17 stablecoins comparables, avec un
  intervalle de Poisson à 90 %. Peu d'événements, donc une fourchette large, et nous le disons.
- **« Le slippage est-il compté ? »** Oui : le coût d'exécution est mesuré par une vraie vente sur le pool. Il n'inclut pas
  la conversion de l'actif en dollars après la vente.
- **« Et si on détient d'autres quantités ? »** `decide` donne le verdict pour n'importe quelles quantités des 3 PT.
  Limite : la perte attendue est celle mesurée pour 1 M de PT, seuls le coût de sortie et la capacité du pool changent.
- **« Ça marche pour n'importe quel token ? »** La découverte, oui (9 PT scannés, et `map` en direct). La simulation est
  écrite pour ces 3 tokens, choisis pour couvrir 3 conceptions d'oracle différentes.
