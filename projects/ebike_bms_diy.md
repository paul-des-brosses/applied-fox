# BMS DIY Vélo Électrique 48V

## Identité
- Nom : BMS DIY Vélo Électrique 48V
- Phase : prototype
- Domaine : hardware
- Dernière mise à jour : 2026-05-12

## Description
Système de gestion de batterie (BMS) pour conversion vélo électrique en pack 48V 13S 20Ah cellules 18650 Samsung INR21700-40T. Surveillance individuelle des 13 séries, équilibrage passif, protection surintensité 30A continu / 50A pic, coupure thermique et seuils tension. Interface I2C vers contrôleur moteur principal pour télémétrie en temps réel et coupure d'urgence. Cible : sécurité fonctionnelle conforme ISO 13849-1 cat. B minimum.

## Objectifs actifs
- Sécurité fonctionnelle équivalente à un BMS commercial certifié, conforme ISO 13849-1 cat. B sur fonction coupure d'urgence
- Coût matériel total BMS : < 60€ vs ~150€ pour solution commerciale équivalente
- Précision mesure tension cellule : ±10 mV pour permettre équilibrage fin et estimation SOC précise

## Prochain rendu
- Date : 2026-08-01
- Nature : démo
- Contenu attendu : pack 13S 20Ah complet équipé BMS, banc d'essai décharge/charge avec courbes, rapport sécurité

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| STM32F103C8T6 | Microcontrôleur principal | validé | critique |
| BQ76940 | AFE Battery monitor 9-15S | en évaluation | critique |
| INA219 | Mesure courant haute précision | validé | critique |
| MOSFET IRFB7430 | Coupure puissance discharge | en évaluation | critique |
| Shunt 1 mΩ 75A | Mesure courant | validé | critique |
| Thermistance NTC 10k 1% | Mesure température cellules | validé | support |
| Cellules Samsung INR21700-40T | Pack 13S2P 4Ah par cellule | validé | critique |
| PCB 2 couches 70µm cuivre | Support et conduction puissance | en évaluation | critique |
| Contrôleur moteur Kelly KLS-S | Contrôleur moteur 48V externe (interface télémétrie) | validé | support |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| STM32CubeIDE | IDE développement | dernière stable | validé |
| FreeRTOS | OS temps réel | 10.x | validé |
| HAL STM32 | Driver bas niveau | 1.8+ | validé |

## Interactions
- BQ76940 → STM32F103C8T6 : tensions individuelles 13 cellules | I2C | 10 Hz
- INA219 → STM32F103C8T6 : courant pack global | I2C | 100 Hz
- Thermistance NTC 10k 1% → STM32F103C8T6 : températures cellules | ADC | 1 Hz × 4 capteurs
- STM32F103C8T6 → MOSFET IRFB7430 : commande on/off + PWM précharge | GPIO + PWM | événementiel
- STM32F103C8T6 → Contrôleur moteur Kelly KLS-S : télémétrie + coupure d'urgence | I2C esclave | 10 Hz

## Contraintes

### Sécurité
- Coupure d'urgence < 50 ms après détection seuil
- Tolérance simple défaut sur fonction coupure (deux MOSFETs en parallèle, contrôle indépendant)
- Watchdog matériel STM32 obligatoire, période < 100 ms

### Électrique
- Tension pack : 36V min décharge, 54.6V max charge complète (4.2V × 13)
- Courant continu : 30A min, 50A pic 10 s
- Précision tension cellule : ±10 mV
- Précision courant : ±50 mA sur plage 30A

### Thermique
- Température fonctionnement cellules : 0°C à 50°C en décharge, 10°C à 45°C en charge
- Dissipation MOSFET pleine puissance : < 5W par MOSFET sans radiateur actif

### Budget
- Coût matériel BMS hors cellules : < 60€

## Contraintes non négociables
- Pas d'utilisation de cellules autre que INR21700-40T validées (chimie connue, datasheet à jour)
- Schéma électrique et firmware open-source pour audit communauté avant mise en service

## Changements
- 2026-05-12 : Création de la fiche pour test de pertinence Applied Fox
