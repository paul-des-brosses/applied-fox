# Station Météo Connectée ESP32

## Identité
- Nom : Station Météo Connectée ESP32
- Phase : prototype
- Domaine : hybride
- Dernière mise à jour : 2026-05-04

## Description
Station météo autonome basée ESP32 mesurant température, humidité, pression atmosphérique et position GPS. Transmission des données par LoRaWAN vers une passerelle locale, fonctionnement sur panneau solaire et batterie LiPo. Destiné à un déploiement outdoor sans intervention humaine pendant 6 mois.

## Objectifs actifs
- Tenir 6 mois d'autonomie en outdoor sans intervention sur batterie LiPo 2000 mAh + panneau solaire 5W
- Transmettre une mesure complète toutes les 15 minutes par LoRaWAN sur 5 km en zone semi-rurale
- Précision température ±0.5°C, humidité ±3% RH, pression ±1 hPa

## Prochain rendu
- Date : 2026-09-15
- Nature : soutenance
- Contenu attendu : prototype fonctionnel, 1 mois de données collectées et visualisées

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| ESP32-WROOM-32E | Microcontrôleur principal + LoRa | validé | critique |
| BME280 | Capteur T°/humidité/pression | validé | critique |
| GP-20U7 | Module GPS | validé | support |
| Panneau solaire 5W 6V | Recharge | validé | critique |
| Batterie LiPo 2000 mAh 3.7V | Stockage énergie | validé | critique |
| Module LoRa SX1276 | Transmission longue distance | validé | critique |
| Boîtier IP65 imprimé 3D | Protection environnement | en évaluation | support |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| ESP-IDF | Framework principal | 5.x | validé |
| LoRaWAN stack LMIC | Stack LoRaWAN | dernière stable | validé |
| MicroPython | Évalué comme alternative | 1.22+ | en évaluation |

## Interactions
- BME280 → ESP32-WROOM-32E : mesures T°/humidité/pression | I2C | 1 lecture/15 min
- GP-20U7 → ESP32-WROOM-32E : trames NMEA position | UART 9600 | 1 lecture/15 min
- ESP32-WROOM-32E → Module LoRa SX1276 : trame LoRaWAN | SPI | 1 émission/15 min
- Panneau solaire 5W 6V → Batterie LiPo 2000 mAh 3.7V : recharge | régulateur MPPT | continu si soleil
- Batterie LiPo 2000 mAh 3.7V → ESP32-WROOM-32E : alimentation | régulateur 3.3V | continu

## Contraintes

### Énergie
- Autonomie cible : 6 mois sans intervention
- Consommation moyenne max : 5 mA en moyenne sur cycle 15 min
- Mode sommeil profond ESP32 entre mesures : < 50 µA

### Environnementales
- Plage température opérationnelle : -10°C à +50°C
- Étanchéité : IP65 minimum
- UV : tenue 6 mois exposition directe soleil

### Connectivité
- Portée LoRaWAN : 5 km en zone semi-rurale
- Latence acceptable : 15 min (pas temps réel)
- Connectivité 5G : N/A
- Connectivité Wi-Fi : TBD, utile en mode debug, à arbitrer selon impact consommation

### Budget
- Coût matériel cible : < 80€ par station
- Coût logiciel : 0€ (open-source uniquement)

## Contraintes non négociables
- Pas de cloud commercial pour les données, passerelle LoRaWAN locale obligatoire
- Code source open-source MIT pour la soutenance

## Changements
- 2026-05-04 : Création de la fiche d'exemple pour la démo du projet Applied Fox
