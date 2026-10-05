import os
import secrets
from datetime import date

from sqlalchemy import select

from .config import ROOT, settings
from .db import SessionLocal
from .domain import create_transaction, learn
from .models import Account, BudgetAllocation, Category, Goal, Household, Member, Period, Receipt, ReceiptItem, Recurring, ReviewTask, User
from .schemas import SplitInput, TransactionInput
from .security import hasher


def seed():
    if settings.app_env == "production":
        raise RuntimeError("Demo seed is forbidden in production")
    password = settings.demo_password or secrets.token_urlsafe(16)
    if len(password) < 10:
        raise RuntimeError("DEMO_PASSWORD needs at least 10 characters")
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == "roch@demo.local")):
            print("Dane demo już istnieją. Logowanie: przycisk „Zobacz wersję demo”.")
            return
        roch = User(name="Roch", email="roch@demo.local", password_hash=hasher.hash(password))
        kaja = User(name="Kaja", email="kaja@demo.local", password_hash=hasher.hash(password))
        db.add_all([roch, kaja])
        db.flush()
        home = Household(name="Dom Rocha i Kai", created_by=roch.id)
        db.add(home)
        db.flush()
        members = [
            Member(household_id=home.id, user_id=u.id, role="owner" if u == roch else "member", created_by=roch.id) for u in [roch, kaja]
        ]
        db.add_all(members)
        main = Account(household_id=home.id, name="Konto wspólne", opening_balance=180000, created_by=roch.id)
        saving = Account(household_id=home.id, name="Oszczędności", kind="savings", opening_balance=680000, created_by=roch.id)
        cash = Account(household_id=home.id, name="Gotówka", kind="cash", opening_balance=25000, created_by=roch.id)
        db.add_all([main, saving, cash])
        defs = [
            ("Mieszkanie", "Potrzeby", "house", "green", 200000),
            ("Jedzenie", "Potrzeby", "basket", "green", 200000),
            ("Rachunki", "Potrzeby", "zap", "amber", 80000),
            ("Transport", "Potrzeby", "car", "blue", 60000),
            ("Przyjemności", "Na co dzień", "coffee", "purple", 70000),
            ("Dom i zakupy", "Na co dzień", "shopping", "blue", 70000),
        ]
        categories = {}
        for name, group, icon, color, _amount in defs:
            category = Category(household_id=home.id, name=name, group=group, icon=icon, color=color, created_by=roch.id)
            db.add(category)
            categories[name] = category
        goal = Goal(
            household_id=home.id,
            name="Poduszka bezpieczeństwa",
            target=2000000,
            opening_amount=480000,
            monthly_amount=140000,
            icon="shield",
            created_by=roch.id,
        )
        holiday = Goal(
            household_id=home.id,
            name="Wakacje we Włoszech",
            target=800000,
            opening_amount=200000,
            monthly_amount=60000,
            icon="sun",
            created_by=roch.id,
        )
        db.add_all([goal, holiday])
        db.flush()
        current = date(2026, 10, 5)
        month = current.strftime("%Y-%m")
        period = Period(household_id=home.id, month=month, planned_income=1000000, created_by=roch.id)
        db.add(period)
        db.flush()
        for name, group, _icon, _color, amount in defs:
            db.add(
                BudgetAllocation(
                    household_id=home.id,
                    period_id=period.id,
                    kind="category",
                    reference_id=categories[name].id,
                    label=name,
                    group=group,
                    amount=amount,
                    created_by=roch.id,
                )
            )
        for person, member in zip([roch, kaja], members, strict=False):
            db.add(
                BudgetAllocation(
                    household_id=home.id,
                    period_id=period.id,
                    kind="pocket",
                    reference_id=member.id,
                    label=person.name,
                    group="Kieszonkowe",
                    amount=60000,
                    created_by=roch.id,
                )
            )
        for g in [goal, holiday]:
            db.add(
                BudgetAllocation(
                    household_id=home.id,
                    period_id=period.id,
                    kind="goal",
                    reference_id=g.id,
                    label=g.name,
                    group="Przyszłość",
                    amount=g.monthly_amount,
                    created_by=roch.id,
                )
            )
        db.flush()
        owner = members[0]

        def movement(key, kind, amount, day, label, category=None, **extra):
            data = TransactionInput(
                kind=kind,
                amount=amount,
                date=current.replace(day=day),
                description=label,
                account_id=main.id,
                allocations=[SplitInput(category_id=categories[category].id, amount=amount)] if category else [],
                **extra,
            )
            return create_transaction(db, owner, data, "seed:" + key)

        movement("income-roch", "income", 600000, 1, "Wynagrodzenie · Roch")
        movement("income-kaja", "income", 400000, 1, "Wynagrodzenie · Kaja")
        rent = Recurring(
            household_id=home.id,
            name="Czynsz i mieszkanie",
            amount=200000,
            day=2,
            category_id=categories["Mieszkanie"].id,
            account_id=main.id,
            created_by=roch.id,
        )
        internet = Recurring(
            household_id=home.id,
            name="Internet",
            amount=6900,
            day=12,
            category_id=categories["Rachunki"].id,
            account_id=main.id,
            created_by=roch.id,
        )
        electricity = Recurring(
            household_id=home.id,
            name="Prąd",
            amount=22000,
            day=20,
            category_id=categories["Rachunki"].id,
            account_id=main.id,
            created_by=roch.id,
        )
        db.add_all([rent, internet, electricity])
        db.flush()
        create_transaction(
            db,
            owner,
            TransactionInput(
                kind="expense",
                amount=200000,
                date=current.replace(day=2),
                description=rent.name,
                account_id=main.id,
                allocations=[SplitInput(category_id=rent.category_id, amount=rent.amount)],
            ),
            f"recurring:{rent.id}:{month}",
            source="recurring",
            source_id=rent.id,
        )
        movement("biedronka", "expense", 18347, 3, "Biedronka", "Jedzenie")
        movement("orlen", "expense", 18000, 3, "Orlen", "Transport")
        movement("coffee", "expense", 4200, 4, "Kawa na mieście", "Przyjemności")
        movement("rossmann", "expense", 6490, 5, "Rossmann", "Dom i zakupy")
        movement("pocket-roch", "pocket", 60000, 1, "Kieszonkowe · Roch", member_id=members[0].id)
        movement("pocket-kaja", "pocket", 60000, 1, "Kieszonkowe · Kaja", member_id=members[1].id)
        movement("goal", "saving", 140000, 1, "Poduszka bezpieczeństwa", goal_id=goal.id, destination_id=saving.id)
        movement("holiday", "saving", 60000, 1, "Wakacje we Włoszech", goal_id=holiday.id, destination_id=saving.id)
        for item, name in [
            ("Chleb żytni", "Jedzenie"),
            ("Mleko 2%", "Jedzenie"),
            ("Papier toaletowy", "Dom i zakupy"),
            ("Desperados", "Przyjemności"),
        ]:
            learn(db, home.id, item, categories[name].id, roch.id)
        # An explicitly marked demo draft; does not count as spending before confirmation.
        from .receipts import storage_path, validated_image

        image = (ROOT / "fixtures/lidl.png").read_bytes()
        path = storage_path("demo-lidl.png")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(validated_image(image))
        path.chmod(0o600)
        import hashlib

        receipt = Receipt(
            household_id=home.id,
            merchant="Lidl",
            date=current.replace(day=4),
            total=13975,
            path=path.name,
            image_hash=hashlib.sha256(image).hexdigest(),
            status="ready",
            provider="fixture",
            created_by=roch.id,
        )
        db.add(receipt)
        db.flush()
        items = [
            ("Chleb żytni", "1", 799, "Jedzenie", 100),
            ("Mleko 2%", "2", 697, "Jedzenie", 100),
            ("Warzywa i owoce", "1", 2382, "Jedzenie", 96),
            ("Desperados", "1", 1799, "Przyjemności", 100),
            ("Papier toaletowy", "1", 1299, "Dom i zakupy", 100),
            ("Parkside — akcesoria", "1", 6999, None, 42),
        ]
        for index, (name, qty, amount, category, confidence) in enumerate(items):
            db.add(
                ReceiptItem(
                    household_id=home.id,
                    receipt_id=receipt.id,
                    name=name,
                    quantity=qty,
                    amount=amount,
                    category_id=categories[category].id if category else None,
                    confidence=confidence,
                    position=index,
                    created_by=roch.id,
                )
            )
        db.add(
            ReviewTask(
                household_id=home.id,
                receipt_id=receipt.id,
                kind="classification",
                title="Lidl · 1 pozycja do sprawdzenia",
                created_by=roch.id,
            )
        )
        db.commit()
        print("Dane demo gotowe: Roch i Kaja, budżet października 2026. Użyj przycisku „Zobacz wersję demo”.")
        if not settings.demo_password:
            env = ROOT / ".env"
            env.write_text(env.read_text().replace("DEMO_PASSWORD=", "DEMO_PASSWORD=" + password, 1))
            os.chmod(env, 0o600)


if __name__ == "__main__":
    seed()
