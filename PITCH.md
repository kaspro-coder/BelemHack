# Pitch, questions du jury, questions aux mentors

Tous les chiffres viennent de `python -m defi_risk.report sUSDe 2026-11-26 1000000` au 10 octobre 2026.
Relance la commande avant de présenter : les données bougent et il faut que tes chiffres collent à l'écran.

## Le pitch (3 minutes)

**1. Le problème (30 s)**
« Une position DeFi n'est pas un actif isolé. Un PT Pendle dépend d'une chaîne, d'un émetteur, d'un oracle,
d'un marché de revente et d'un marché de prêt qui l'utilise en garantie. Si un maillon casse, on perd
de l'argent, et la ligne du portefeuille ne montre rien de tout ça. »

**2. Ce que fait l'outil (30 s)**
« On donne une position. L'outil découvre ses dépendances sur des données réelles, chiffre ce que
coûte chaque scénario de panne, et sort un verdict : rester, sortir, ou "les données ne tranchent pas".
Personne ne saisit de probabilité : on ne décide pas sous la peur. »

**3. Ce qu'il a trouvé sur PT-sUSDe (1 min)**
- 15 éléments dans le graphe de dépendances, découverts automatiquement, dont l'oracle du marché de prêt
  lu directement sur la blockchain : il a un oracle primaire et un oracle de secours, et d'après la liste
  de ses flux de prix le primaire ne lit aucun prix USDe/USD. Il ne devrait donc pas voir un décrochage
  de USDe pendant le délai de contestation (16 h). C'est une déduction, pas un test.
- Le marché de prêt n'a que 13 emprunteurs. Deux baleines portent 91 % de la dette. La plus exposée
  est à 0,97 % de la liquidation.
- Si USDe baisse de 4 %, 3,4 à 7,7 M$ de garanties sont saisies, pour un pool qui absorbe 4,6 M$ en
  une vente. Ce risque de cascade n'est visible nulle part dans le prix du PT.

**4. Le verdict (30 s)**
« Pour 1 M$, le verdict est UNCLEAR. Rester est meilleur à l'estimation centrale, sortir est meilleur
au haut de la fourchette. L'outil le dit au lieu de forcer une réponse, et suggère de réduire la taille. »

**5. Limites, dites-les toi-même (30 s)**
« Le risque de décrochage vient de 17 stablecoins comparables, avec seulement 2 événements : la fourchette
est large. Seuls deux scénarios sont chiffrés. Le choc de rendement est une hypothèse. »

## Les questions probables et les réponses honnêtes

**Pourquoi UNCLEAR et pas un verdict net ?**
Parce que sur cette position la prime de risque payée par le marché (1 % au-dessus des bons du Trésor)
est du même ordre que le risque estimé. Forcer STAY ou EXIT serait fabriquer de la précision.

**D'où vient la probabilité de 0,65 % ?**
Du taux observé de décrochages durables d'au moins 3 % sur 46 jours, sur 17 stablecoins non adossés à
du cash de plus de 100 M$. Intervalle à 90 % : 0,27 à 2,04 %. Deux événements seulement.

**Pourquoi seulement 17 coins ?**
Pour comparer USDe à des actifs de sa taille. Avec les coins de plus de 10 M$ on obtient 2,8 %.
La taille est mesurée aujourd'hui, donc les morts sont sous-représentés : le vrai risque est plutôt plus haut.

**Le chiffre de 7,7 M$ saisis est-il fiable ?**
Il dépend de mon hypothèse de choc de rendement. Sans elle : 3,4 M$. Je montre les deux.

**Pourquoi 5× pour le choc de rendement ?**
C'est un jugement, pas une mesure. Il n'affecte que les pertes temporaires (valeur de marché), pas la
perte définitive qui sert à la décision.

**Pourquoi le taux des bons du Trésor à 3 mois ?**
C'est l'alternative sans risque en dollars. Un autre benchmark (fonds monétaire tokenisé, prêt USDC)
changerait le carry abandonné. C'est un choix de modélisation, et une bonne question pour Belem.

**Qu'est-ce qui est vérifié et qu'est-ce qui ne l'est pas ?**
Chaque lien du graphe porte une étiquette : mesuré (données vivantes), documenté (doc officielle
d'Ethena) ou non vérifié (source tierce). Seul Bybit est confirmé comme exchange de couverture d'Ethena.

**Votre outil fonctionne-t-il sur un autre actif ?**
Honnêtement, pas encore sans effort : le lien PT vers Ethena est codé à la main (`ISSUERS` dans
`discover.py`), et l'oracle est lu pour le format Morpho primaire/secours. La découverte du reste
(Pendle, Morpho, liquidité, emprunteurs) est automatique.

**Avez-vous testé le modèle contre un vrai événement ?**
Pas de backtest. Le seul point de comparaison est Bybit (février 2025) : USDe est passé sous 0,96 $
puis est remonté. Je l'utilise pour dimensionner le scénario, pas pour le valider.

## Questions à poser aux mentors de Belem

1. **Répartition des couvertures d'Ethena** : quelle part sur chaque exchange ? Aujourd'hui le modèle suppose
   4 exchanges et aucune répartition, parce qu'Ethena ne la publie pas.
2. **Taux de référence sans risque** : quelle alternative utilisez-vous pour juger le carry d'un PT ?
   J'utilise le bon du Trésor US 3 mois (4,05 %).
3. **Oracle Morpho** : quel est le seuil d'écart qui déclenche la contestation ? Je lis un délai de 16 h
   mais pas le seuil, qui fixe la durée réelle de la fenêtre où l'oracle est aveugle.
4. **Probabilité de décrochage** : 0,65 % (plage 0,27 à 2,04 %) vous paraît-il plausible pour USDe sur
   46 jours ? Quel ordre de grandeur utilisez-vous en interne ?
5. **Baleines Morpho** : suivez-vous la distance à la liquidation des plus gros emprunteurs comme
   signal d'alerte ? À quel seuil sortez-vous ?
6. **Cas de référence** : pouvez-vous partager une structure de portefeuille réelle (le brief dit que vous
   en avez) pour tester l'outil sur autre chose que PT-sUSDe ?
7. **Pertes définitives après un piratage d'exchange** : y a-t-il des cas où une perte a réellement
   atteint le stablecoin ? Je n'ai qu'un précédent (Bybit), sans perte durable.

## Avant de monter sur scène

- [ ] Relancer `python -m defi_risk.dashboard` pour rafraîchir les chiffres, puis les relire sur la page.
- [ ] Lancer le serveur : `cd dashboard && python -m http.server 8765`, ouvrir http://localhost:8765.
- [ ] Avoir le terminal prêt avec `python -m defi_risk.report` en secours si la page plante.
- [ ] Mettre le dépôt en public seulement si le règlement le demande. Ne pas y mettre le PDF de Belem.
- [ ] Apprendre les trois chiffres : 13 emprunteurs, 91 % de la dette chez deux comptes, 0,97 % de la liquidation.
