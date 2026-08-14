import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.models import User
from apps.spots.models import WaterSpot
from apps.conditions.models import WaterCondition, ConditionScore
from apps.forecasts.models import WaterForecast

class Command(BaseCommand):
    help = 'Seed dummy data for PongDang'

    def handle(self, *args, **kwargs):
        self.stdout.write("Deleting old data...")
        WaterForecast.objects.all().delete()
        ConditionScore.objects.all().delete()
        WaterCondition.objects.all().delete()
        WaterSpot.objects.all().delete()

        spot_names = [
            ("해운대 해수욕장", "sea"), ("광안리 해수욕장", "sea"), ("경포대 해수욕장", "sea"), 
            ("속초 해수욕장", "sea"), ("중문 색달 해변", "sea"), ("협재 해수욕장", "sea"),
            ("을왕리 해수욕장", "sea"), ("대천 해수욕장", "sea"), ("송정 해수욕장", "sea"),
            ("송지호 해수욕장", "sea"), ("가평 용추계곡", "valley"), ("명지계곡", "valley"), 
            ("지리산 뱀사골", "valley"), ("설악산 천불동계곡", "valley"), ("쌍곡계곡", "valley"),
            ("수안보 온천", "hotspring"), ("덕구 온천", "hotspring"), ("온양 온천", "hotspring"),
            ("백암 온천", "hotspring"), ("도고 온천", "hotspring"), ("동막 해수욕장 갯벌", "tidal_flat"),
            ("선재도 갯벌", "tidal_flat"), ("제부도 갯벌", "tidal_flat"), ("무창포 갯벌", "tidal_flat"),
            ("캐리비안베이", "waterpark"), ("오션월드", "waterpark"), ("청평호", "lake"), 
            ("충주호", "lake"), ("정방폭포", "waterfall"), ("천지연폭포", "waterfall")
        ]
        
        # Add more to reach ~50
        for i in range(20):
            spot_names.append((f"테스트 스팟 {i+1}", random.choice(["sea", "valley", "lake"])))

        self.stdout.write(f"Creating {len(spot_names)} spots...")
        
        activities = ["swim", "surf", "relax", "mudflat", "onsen", "rafting"]
        now = timezone.now()

        for name, s_type in spot_names:
            spot = WaterSpot.objects.create(
                name=name,
                type=s_type,
                lat=35.0 + random.uniform(0, 3),
                lng=126.0 + random.uniform(0, 3),
                region="강원" if random.random() > 0.5 else "부산/경남",
                address=f"테스트 주소 {name}",
                tags=["#여름휴가", "#물멍", "#가족여행"],
                image_url=f"https://picsum.photos/seed/{random.randint(1, 1000)}/800/600",
                description=f"{name}은 아주 멋진 곳입니다."
            )

            # Condition
            WaterCondition.objects.create(
                spot=spot,
                water_temp=random.uniform(15.0, 28.0),
                air_temp=random.uniform(20.0, 35.0),
                wind_speed=random.uniform(0.5, 10.0),
                wave_height=random.uniform(0.1, 2.5),
                water_quality_grade=random.randint(1, 3),
                fetched_at=now
            )

            # Scores
            for act in activities:
                score = random.randint(30, 98)
                if s_type == 'sea' and act == 'surf': score = random.randint(60, 98)
                if s_type == 'hotspring' and act == 'onsen': score = random.randint(80, 98)
                
                ConditionScore.objects.create(
                    spot=spot,
                    activity=act,
                    score=score,
                    computed_at=now
                )

            # Forecasts (7 days)
            for d in range(1, 8):
                WaterForecast.objects.create(
                    spot=spot,
                    forecast_date=(now + timedelta(days=d)).date(),
                    predicted_index=random.randint(50, 95),
                    computed_at=now
                )

        self.stdout.write(self.style.SUCCESS('Successfully seeded dummy data!'))
