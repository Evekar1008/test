from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HaenelStatus:
    ok: bool
    current_shelf: str
    shelf_in_access: str | None
    return_value: int
    message: str = ""


class HaenelClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.current_shelf = ""

    def read_status(self) -> HaenelStatus:
        """Call readStatusV02 or read_status."""
        return HaenelStatus(
            ok=True,
            current_shelf=self.current_shelf,
            shelf_in_access=self.current_shelf or None,
            return_value=0,
            message="Simulated Host-Web status",
        )

    def get_shelf(
        self,
        shelf: str,
        access_point: int,
        text_lines: list[str] | None = None,
    ) -> HaenelStatus:
        """Call getShelfV02 or get_shelf."""
        self.current_shelf = str(shelf)
        return HaenelStatus(
            ok=True,
            current_shelf=str(shelf),
            shelf_in_access=str(shelf),
            return_value=0,
            message=f"Simulated get shelf {shelf} to access point {access_point}",
        )

    def store_shelf(self, access_point: int) -> HaenelStatus:
        """Call store_shelf."""
        shelf = self.current_shelf
        self.current_shelf = ""
        return HaenelStatus(
            ok=True,
            current_shelf=shelf,
            shelf_in_access=None,
            return_value=0,
            message=f"Simulated store shelf from access point {access_point}",
        )

    def confirm(self) -> bool:
        """Call confirmV01 if operator confirmation is needed."""
        return True
