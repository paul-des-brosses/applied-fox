# Tracker LoRa Faune Sauvage

## Identité
- Nom : Tracker LoRa Faune Sauvage
- Phase : exploration
- Domaine : hardware
- Dernière mise à jour : 2026-05-12

## Description
Balise GPS basse consommation destinée à être fixée sur des animaux sauvages de moyenne taille (cervidés, sangliers) dans le cadre d'un programme de suivi écologique. Acquisition GPS multi-constellations toutes les 30 minutes en mouvement, transmission LoRa P2P vers passerelles fixes en lisière de forêt. Cible : autonomie 18 mois sur batterie primaire lithium non rechargeable, poids total < 80 g.

## Objectifs actifs
- Tenir 18 mois d'autonomie sur batterie primaire lithium non rechargeable
- Poids total balise harnais inclus : < 80 g
- Portée LoRa P2P en milieu forestier dense : 1.5 km minimum vers passerelles fixes

## Prochain rendu
- Date : 2026-12-01
- Nature : livraison client
- Contenu attendu : 10 balises terrain, 1 mois de retours opérationnels, rapport d'autonomie réelle

## Composants
| Composant | Rôle | Statut décisionnel | Rôle pipeline |
|-----------|------|--------------------|---------------|
| RAK3172 | Module LoRa + STM32WL intégré | en évaluation | critique |
| u-blox NEO-M9N | GPS multi-constellations | validé | critique |
| LIS3DH | Accéléromètre détection mouvement | validé | support |
| Batterie ER18505 LiSOCl2 3.6V 4000mAh | Source primaire haute densité | en évaluation | critique |
| Antenne LoRa 868 MHz quart d'onde | Antenne intégrée boîtier | validé | critique |
| Boîtier ABS étanche moulé | Protection terrain | en évaluation | critique |
| Sangle harnais nylon souple | Fixation animal | validé | support |

## Stack software
| Outil | Rôle | Version | Statut décisionnel |
|-------|------|---------|--------------------|
| STM32CubeIDE | IDE développement | dernière stable | validé |
| LoRaMac-node Semtech | Stack LoRa P2P | 4.7+ | en évaluation |
| u-blox AssistNow Offline | Aide acquisition GPS rapide | dernière stable | en évaluation |

## Interactions
- u-blox NEO-M9N → RAK3172 : trames position | UART | 1/30 min en mouvement
- LIS3DH → RAK3172 : interruption seuil mouvement | I2C + GPIO INT | événementiel
- RAK3172 → Antenne LoRa 868 MHz quart d'onde : émission trame position | RF | 1 émission/30 min
- Batterie ER18505 LiSOCl2 3.6V 4000mAh → RAK3172 : alimentation | régulateur LDO basse conso | continu

## Contraintes

### Énergie
- Autonomie cible : 18 mois minimum, 24 mois souhaité
- Consommation moyenne max : 25 µA sur cycle complet 30 min
- Mode arrêt profond entre acquisitions : < 5 µA

### Mécanique
- Poids total balise + harnais : < 80 g
- Résistance choc : chute 2 m sur sol rocailleux
- Étanchéité : IP67 minimum (immersion ponctuelle possible)

### Réglementaire
- Conformité émissions LoRa 868 MHz Europe ERC 70-03 (duty cycle 1%)
- Marquage CE pour usage civil

### Budget
- Coût matériel cible : < 150€ par balise

## Contraintes non négociables
- Aucune transmission cellulaire (4G/5G), exclusivement LoRa P2P pour préserver l'autonomie
- Données GPS chiffrées en transit (AES-128 minimum) pour éviter géolocalisation malveillante de la faune

## Changements
- 2026-05-12 : Création de la fiche pour test de pertinence Applied Fox
