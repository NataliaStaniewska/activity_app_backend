from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityEntry
from app.schemas.analytics import (
    ActivityRankings,
    ActivityStatistic,
    AverageMetric,
    ContextPreferences,
    ContextRankings,
    DiversityStatistic,
    DistributionItem,
    NamedStatistic,
    ProfileDataVolume,
    ProfileSummary,
    RankedActivity,
    RankedContext,
    RecommendationProfile,
    StatisticsResponse,
    UserStatement,
)

MIN_RANKING_OBSERVATIONS = 2
RANKING_LIMIT = 5


def _average(values: list[float]) -> AverageMetric:
    return AverageMetric(
        mean=round(fmean(values), 2) if values else None,
        observations=len(values),
    )


def _rankings(
    items: list[NamedStatistic],
    *,
    name: Callable[[NamedStatistic], str],
) -> ContextRankings:
    eligible = [item for item in items if item.count >= MIN_RANKING_OBSERVATIONS]

    def ranked(
        metric: Callable[[NamedStatistic], AverageMetric],
        *,
        reverse: bool,
    ) -> list[RankedContext]:
        ordered = sorted(
            eligible,
            key=lambda item: (
                metric(item).mean if metric(item).mean is not None else 0,
                name(item).casefold(),
            ),
            reverse=reverse,
        )[:RANKING_LIMIT]
        return [
            RankedContext(
                name=name(item),
                occurrences=item.count,
                mean_mood_after=item.mean_mood_after,
                mean_rating=item.mean_rating,
            )
            for item in ordered
        ]

    return ContextRankings(
        highest_mood_after=ranked(lambda item: item.mean_mood_after, reverse=True),
        lowest_mood_after=ranked(lambda item: item.mean_mood_after, reverse=False),
        highest_rating=ranked(lambda item: item.mean_rating, reverse=True),
        lowest_rating=ranked(lambda item: item.mean_rating, reverse=False),
    )


def _activity_rankings(items: list[ActivityStatistic]) -> ActivityRankings:
    eligible = [item for item in items if item.count >= MIN_RANKING_OBSERVATIONS]

    def ranked(
        metric: Callable[[ActivityStatistic], AverageMetric],
        *,
        reverse: bool,
    ) -> list[RankedActivity]:
        ordered = sorted(
            eligible,
            key=lambda item: (
                metric(item).mean if metric(item).mean is not None else 0,
                item.activity_name.casefold(),
            ),
            reverse=reverse,
        )[:RANKING_LIMIT]
        return [
            RankedActivity(
                activity_name=item.activity_name,
                occurrences=item.count,
                mean_mood_after=item.mean_mood_after,
                mean_rating=item.mean_rating,
            )
            for item in ordered
        ]

    return ActivityRankings(
        highest_mood_after=ranked(lambda item: item.mean_mood_after, reverse=True),
        lowest_mood_after=ranked(lambda item: item.mean_mood_after, reverse=False),
        highest_rating=ranked(lambda item: item.mean_rating, reverse=True),
        lowest_rating=ranked(lambda item: item.mean_rating, reverse=False),
    )


def analyze_activities(db: Session) -> tuple[StatisticsResponse, list[ActivityEntry]]:
    entries = list(
        db.scalars(select(ActivityEntry).order_by(ActivityEntry.date, ActivityEntry.id))
    )

    activity_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"mood_after": [], "rating": []}
    )
    category_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"mood_after": [], "rating": []}
    )
    location_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"mood_after": [], "rating": []}
    )
    company_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"mood_after": [], "rating": []}
    )
    mood_distribution: Counter[int] = Counter()
    mood_changes: list[float] = []

    for entry in entries:
        activity_values[entry.activity_name]["mood_after"].append(entry.mood_after)
        activity_values[entry.activity_name]["rating"].append(entry.rating)
        mood_distribution[entry.mood_after] += 1
        location_values[entry.location_type]["mood_after"].append(entry.mood_after)
        location_values[entry.location_type]["rating"].append(entry.rating)
        company_values[entry.company_type]["mood_after"].append(entry.mood_after)
        company_values[entry.company_type]["rating"].append(entry.rating)

        for category in set(entry.categories):
            category_values[category]["mood_after"].append(entry.mood_after)
            category_values[category]["rating"].append(entry.rating)

        if entry.mood_before is not None:
            mood_changes.append(entry.mood_after - entry.mood_before)

    activity_stats = [
        ActivityStatistic(
            activity_name=name,
            count=len(values["mood_after"]),
            mean_mood_after=_average(values["mood_after"]),
            mean_rating=_average(values["rating"]),
        )
        for name, values in sorted(
            activity_values.items(), key=lambda item: item[0].casefold()
        )
    ]

    def named_stats(
        groups: dict[str, dict[str, list[float]]],
    ) -> list[NamedStatistic]:
        return [
            NamedStatistic(
                name=name,
                count=len(values["mood_after"]),
                mean_mood_after=_average(values["mood_after"]),
                mean_rating=_average(values["rating"]),
            )
            for name, values in sorted(groups.items(), key=lambda item: item[0].casefold())
        ]

    category_stats = named_stats(category_values)
    stats = StatisticsResponse(
        total_entries=len(entries),
        distinct_activities=len(activity_values),
        distinct_categories=len(category_values),
        activity_occurrences=activity_stats,
        mood_after_distribution=[
            DistributionItem(value=value, count=count)
            for value, count in sorted(mood_distribution.items())
        ],
        categories=category_stats,
        location_types=named_stats(location_values),
        company_types=named_stats(company_values),
        diversity=DiversityStatistic(
            unique_activities=len(activity_values),
            unique_categories=len(category_values),
        ),
        mean_mood_change=_average(mood_changes),
    )
    return stats, entries


def _context_preferences(items: Iterable[NamedStatistic]) -> ContextRankings:
    item_list = list(items)
    return _rankings(item_list, name=lambda item: item.name)


def build_recommendation_profile(db: Session) -> RecommendationProfile:
    stats, entries = analyze_activities(db)
    activity_rankings = _activity_rankings(stats.activity_occurrences)
    category_rankings = _context_preferences(stats.categories)
    context_preferences = ContextPreferences(
        categories=category_rankings,
        location_types=_context_preferences(stats.location_types),
        company_types=_context_preferences(stats.company_types),
    )

    frequently_performed = sorted(
        stats.activity_occurrences,
        key=lambda item: (-item.count, item.activity_name.casefold()),
    )[:RANKING_LIMIT]
    existing_activities = sorted(
        stats.activity_occurrences,
        key=lambda item: item.activity_name.casefold(),
    )

    statements = [
        UserStatement(
            activity_name=entry.activity_name,
            likes=entry.likes,
            dislikes=entry.dislikes,
        )
        for entry in entries
        if entry.likes is not None or entry.dislikes is not None
    ]

    return RecommendationProfile(
        summary=ProfileSummary(
            total_entries=stats.total_entries,
            distinct_activities=stats.distinct_activities,
            distinct_categories=stats.distinct_categories,
            mean_mood_change=stats.mean_mood_change,
        ),
        data_volume=ProfileDataVolume(
            total_entries=stats.total_entries,
            distinct_activities=stats.distinct_activities,
            distinct_categories=stats.distinct_categories,
            minimum_observations_for_rankings=MIN_RANKING_OBSERVATIONS,
        ),
        frequently_performed=[
            {
                "activityName": item.activity_name,
                "occurrences": item.count,
            }
            for item in frequently_performed
        ],
        activity_preferences=activity_rankings,
        category_preferences=category_rankings,
        context_preferences=context_preferences,
        user_statements=statements,
        existing_activities=[
            {
                "activityName": item.activity_name,
                "occurrences": item.count,
            }
            for item in existing_activities
        ],
        limitations=[
            "The profile aggregates all database entries; activities are not assigned to users.",
            "Only observed associations are summarized; they do not establish causal effects.",
            "Ratings are self-reported and may reflect context not captured by these fields.",
            (
                "Rankings require at least "
                f"{MIN_RANKING_OBSERVATIONS} observations; sparse groups are omitted."
            ),
            "This profile does not predict future mood or guarantee recommendation outcomes.",
        ],
    )


def build_statistics(db: Session) -> StatisticsResponse:
    stats, _ = analyze_activities(db)
    return stats
