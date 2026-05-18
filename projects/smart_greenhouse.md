# Serre Connectée Autonome

## Identité
- Nom : Serre Connectée Autonome
- Phase : prototype
- Domaine : hybride
- Dernière mise à jour : 2026-05-12

## Description
Système de pilotage automatique d'une serre 10 m² destinée à la culture maraîchère sous abri. Mesure de température, humidité de l'air, humidité du sol et CO2, puis déclenchement automatique d'arrosage goutte-à-goutte et de ventilation selon des seuils paramétrables. Pilotage local par ESP32, supervision via dashboard web auto-hébergé. Objectif : réduction de 40% de la consommation d'eau par rapport à un arrosage manuel programmé.

## Objectifs actifs
- Réduire la consommation d'eau de 40% vs arrosage manuel programmé fixe sur une saison complète
- Maintenir la température entre 15°C et 30°C par ventilation automatique sans actionneur de chauffage
- Tenir 12 mois sans intervention sur capteurs (étalonnage compris)

## Prochain rendu
- Date : 2026-10-01
- Nature : démo
- Contenu attendu : prototype installé en serre réelle, 1 saison de données comparée à témoin manuel

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| ESP32-S3 DevKitC | Microcontrôleur principal | validé | critique |
| SHT31-D | Capteur T°/humidité air | validé | critique |
| MH-Z19B | Capteur CO2 NDIR | validé | critique |
| Capacitive soil moisture sensor v2.0 | Humidité sol (3 zones) | en évaluation | critique |
| Pompe péristaltique 12V DC | Arrosage goutte-à-goutte | validé | critique |
| Ventilateur 12V 120mm PWM | Ventilation active | validé | support |
| Relais SSR 12V/240V | Pilotage actionneurs | validé | support |
| Alimentation 12V 5A | Source réseau | validé | critique |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| ESP-IDF | Framework principal | 5.x | validé |
| ESPHome | Alternative envisagée | 2024.x | en évaluation |
| InfluxDB | Stockage time-series local | 2.x | validé |
| Grafana | Dashboard supervision | dernière stable | validé |

## Interactions
- SHT31-D → ESP32-S3 DevKitC : mesures T°/humidité | I2C | 1/min
- MH-Z19B → ESP32-S3 DevKitC : mesure CO2 | UART | 1/min
- Capacitive soil moisture sensor v2.0 → ESP32-S3 DevKitC : mesures humidité sol | ADC | 1/min × 3 zones
- ESP32-S3 DevKitC → Relais SSR 12V/240V : commande pompe et ventilateur | GPIO | événementiel
- ESP32-S3 DevKitC → InfluxDB : push métriques | Wi-Fi MQTT | 1/min

## Contraintes

### Énergie
- Alimentation réseau 230V, pas d'autonomie batterie requise
- Consommation idle ESP32 : < 100 mA

### Précision capteurs
- T° : ±0.3°C
- Humidité air : ±2% RH
- CO2 : ±50 ppm
- Humidité sol : capacitif, dérive max 5% sur 6 mois

### Connectivité
- Wi-Fi local exclusif, pas d'accès cloud externe pour les données
- Latence commande arrosage : < 5 s après seuil franchi

### Budget
- Coût matériel cible : < 200€ pour la serre 10 m² complète

## Contraintes non négociables
- Données capteurs et historique strictement locaux, pas de cloud commercial
- Code source open-source MIT pour partage post-soutenance

## Changements
- 2026-05-12 : Création de la fiche pour test de pertinence Applied Fox
