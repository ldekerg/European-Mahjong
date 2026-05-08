# Calibration du freeze COVID

## Principe

Le freeze COVID correspond à la période pendant laquelle les tournois EMA ont été annulés.
Durant cette période, le classement n'était pas mis à jour et **la durée de vie des tournois
antérieurs a été prolongée** : les semaines freeze ne comptent pas dans les 104 semaines
actives d'un tournoi.

**Règle implémentée :**
- Un tournoi compte pendant **104 semaines actives** (hors freeze)
- Semaines 1-52 actives → contribution 100%
- Semaines 53-104 actives → contribution 50%
- Au-delà → 0%, tournoi expiré
- Les tournois joués **pendant** le freeze comptent normalement (le freeze prolonge juste la fenêtre)

## Constantes calibrées

```python
FREEZE_DEBUT = date(2020, 2, 24)  # lundi précédant les premières annulations
FREEZE_FIN   = date(2022, 3, 28)  # reprise des tournois EMA
```

Durée : **109 semaines** (~2 ans 2 mois)

## Jeux de données de référence

### Semaine du 27 février 2023

| Joueur         | EMA ID   | Score att. | Score obtenu | NbT att. | NbT obtenu |
|----------------|----------|------------|--------------|----------|------------|
| BAZZOCCHI      | 07000002 | 951        | 950.99       | 9        | 9 ✓        |
| RÍOS NAVARRO   | 10990043 | 909        | 909.30       | 11       | 11 ✓       |
| DE KERGOMMEAUX | 04290031 | 879        | 877.49       | 10       | 10 ✓       |
| RAK            | 04090026 | 878        | 872.10       | 9        | 9 ✓        |
| NIEUWENDIJK    | 08010667 | 875        | 874.71       | 7        | 7 ✓        |

### Semaine du 4 mars 2024

| Joueur         | EMA ID   | Score att. | Score obtenu | NbT att. | NbT obtenu |
|----------------|----------|------------|--------------|----------|------------|
| DE KERGOMMEAUX | 04290031 | 920        | 919.52       | 11       | 11 ✓       |
| BAZZOCCHI      | 07000002 | 908        | 908.19       | 9        | 9 ✓        |
| CHRISTIANSEN   | 03000049 | 900        | 900.21       | 5        | 5 ✓        |
| RAK            | 04090026 | 898        | 898.06       | 10       | 10 ✓       |
| BROERS         | 08010028 | 892        | 891.89       | 7        | 7 ✓        |

## Cas particulier : tournoi 317

Le tournoi **GOURMET CUP 2019 - AUSTRIA** (ema_id=317) avait une date mal inférée (2018
au lieu de 2019) en raison d'un format "2-3 February" sans année sur la page EMA.
Date corrigée manuellement à `2019-02-02`. Ce tournoi est actif à 50% au 27/02/2023
(n_act=104 semaines actives exactement), ce qui permet d'obtenir le bon compte de
tournois pour BAZZOCCHI.

## Méthode de calibration

1. Fixer FREEZE_FIN à la reprise observable des tournois (fin mars 2022)
2. Faire varier FREEZE_DEBUT par pas d'une semaine
3. Minimiser l'erreur sur score et NbT pour les 10 joueurs de référence (5 × 2 dates)
4. Les dates de référence EMA sont décalées d'une semaine par rapport aux dates
   annoncées, car certains tournois "basculent" de 100% à 50% exactement à cette semaine
