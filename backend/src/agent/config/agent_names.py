"""
Agent name lists for randomly assigning friendly names to planner and worker agents.

This configuration provides personality and character to the AI agents by assigning
them recognisable names from popular children's television shows and Disney films.
"""

import random
from typing import List


# Names for PlannerAgent - Adults from TV shows + Disney Princesses + Ryder
PLANNER_NAMES: List[str] = [
    # Bluey adults
    "Uncle Stripe",
    "Aunt Trixie",
    "Uncle Rad",
    "Frisky",
    "Wendy",
    "Janelle",
    "Pat",
    "Calypso",
    # Peppa Pig adults
    "Daddy Pig",
    "Mummy Pig",
    "Grandpa Pig",
    "Granny Pig",
    "Uncle Pig",
    "Aunty Pig",
    "Madame Gazelle",
    "Miss Rabbit",
    # Ryder from Paw Patrol (special inclusion as requested)
    "Ryder",
    # Disney Princesses
    "Snow White",
    "Cinderella",
    "Aurora",
    "Ariel",
    "Belle",
    "Jasmine",
    "Pocahontas",
    "Mulan",
    "Tiana",
    "Rapunzel",
    "Merida",
    "Anna",
    "Elsa",
    "Moana",
    "Raya",
]

# Names for WorkerAgent - Children and dogs from various TV shows
WORKER_NAMES: List[str] = [
    # Paw Patrol dogs
    "Marshall",
    "Rubble",
    "Chase",
    "Rocky",
    "Zuma",
    "Skye",
    "Everest",
    "Tracker",
    "Rex",
    "Liberty",
    "Coral",
    "Shade",
    # Sofia the First children
    "Sofia",
    "Amber",
    "James",
    "Clio",
    "Hildegard",
    "Jun",
    "Zandar",
    # Spidey and His Amazing Friends
    "Peter Parker",
    "Miles Morales",
    "Gwen Stacy",
    "Spin",
    "Ghost-Spider",
    # Peppa Pig children
    "Peppa",
    "George",
    "Rebecca Rabbit",
    "Pedro Pony",
    "Suzy Sheep",
    "Candy Cat",
    "Emily Elephant",
    "Danny Dog",
    "Zoe Zebra",
    "Freddy Fox",
    "Gabriella Goat",
    "Gerald Giraffe",
    # Bluey children
    "Bluey",
    "Bingo",
    "Muffin",
    "Socks",
    "Coco",
    "Snickers",
    "Honey",
    "Mackenzie",
    "Jack",
    "Rusty",
    "Indy",
    "Judo",
    "Lila",
    "Chloe",
]


def get_random_planner_name() -> str:
    """Get a random name for a planner agent."""
    return random.choice(PLANNER_NAMES)


def get_random_worker_name() -> str:
    """Get a random name for a worker agent."""
    return random.choice(WORKER_NAMES)
