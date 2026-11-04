from django.core.management.base import BaseCommand

from planner.seed import seed


class Command(BaseCommand):
    help = "Load the demo world (areas, people, slots, activities). --wipe deletes everything first."

    def add_arguments(self, parser):
        parser.add_argument("--wipe", action="store_true")

    def handle(self, *args, **opts):
        owner = seed(wipe=opts["wipe"])
        self.stdout.write(f"seeded; owner={owner.name} token={owner.token}")
