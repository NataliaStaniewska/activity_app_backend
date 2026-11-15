from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AverageMetric(APIModel):
    mean: float | None
    observations: int


class ActivityStatistic(APIModel):
    activity_name: str = Field(alias="activityName")
    count: int
    mean_mood_after: AverageMetric = Field(alias="meanMoodAfter")
    mean_rating: AverageMetric = Field(alias="meanRating")


class NamedStatistic(APIModel):
    name: str
    count: int
    mean_mood_after: AverageMetric = Field(alias="meanMoodAfter")
    mean_rating: AverageMetric = Field(alias="meanRating")


class DistributionItem(APIModel):
    value: int
    count: int


class DiversityStatistic(APIModel):
    unique_activities: int = Field(alias="uniqueActivities")
    unique_categories: int = Field(alias="uniqueCategories")


class StatisticsResponse(APIModel):
    total_entries: int = Field(alias="totalEntries")
    distinct_activities: int = Field(alias="distinctActivities")
    distinct_categories: int = Field(alias="distinctCategories")
    activity_occurrences: list[ActivityStatistic] = Field(alias="activityOccurrences")
    mood_after_distribution: list[DistributionItem] = Field(
        alias="moodAfterDistribution"
    )
    categories: list[NamedStatistic]
    location_types: list[NamedStatistic] = Field(alias="locationTypes")
    company_types: list[NamedStatistic] = Field(alias="companyTypes")
    diversity: DiversityStatistic
    mean_mood_change: AverageMetric = Field(alias="meanMoodChange")


class RankedActivity(APIModel):
    activity_name: str = Field(alias="activityName")
    occurrences: int
    mean_mood_after: AverageMetric = Field(alias="meanMoodAfter")
    mean_rating: AverageMetric = Field(alias="meanRating")


class RankedContext(APIModel):
    name: str
    occurrences: int
    mean_mood_after: AverageMetric = Field(alias="meanMoodAfter")
    mean_rating: AverageMetric = Field(alias="meanRating")


class ActivityRankings(APIModel):
    highest_mood_after: list[RankedActivity] = Field(alias="highestMoodAfter")
    lowest_mood_after: list[RankedActivity] = Field(alias="lowestMoodAfter")
    highest_rating: list[RankedActivity] = Field(alias="highestRating")
    lowest_rating: list[RankedActivity] = Field(alias="lowestRating")


class ContextRankings(APIModel):
    highest_mood_after: list[RankedContext] = Field(alias="highestMoodAfter")
    lowest_mood_after: list[RankedContext] = Field(alias="lowestMoodAfter")
    highest_rating: list[RankedContext] = Field(alias="highestRating")
    lowest_rating: list[RankedContext] = Field(alias="lowestRating")


class ContextPreferences(APIModel):
    categories: ContextRankings
    location_types: ContextRankings = Field(alias="locationTypes")
    company_types: ContextRankings = Field(alias="companyTypes")


class ActivityFrequency(APIModel):
    activity_name: str = Field(alias="activityName")
    occurrences: int


class UserStatement(APIModel):
    activity_name: str = Field(alias="activityName")
    likes: str | None
    dislikes: str | None


class ProfileSummary(APIModel):
    total_entries: int = Field(alias="totalEntries")
    distinct_activities: int = Field(alias="distinctActivities")
    distinct_categories: int = Field(alias="distinctCategories")
    mean_mood_change: AverageMetric = Field(alias="meanMoodChange")


class ProfileDataVolume(APIModel):
    total_entries: int = Field(alias="totalEntries")
    distinct_activities: int = Field(alias="distinctActivities")
    distinct_categories: int = Field(alias="distinctCategories")
    minimum_observations_for_rankings: int = Field(
        alias="minimumObservationsForRankings"
    )


class RecommendationProfile(APIModel):
    summary: ProfileSummary
    data_volume: ProfileDataVolume = Field(alias="dataVolume")
    frequently_performed: list[ActivityFrequency] = Field(alias="frequentlyPerformed")
    activity_preferences: ActivityRankings = Field(alias="activityPreferences")
    category_preferences: ContextRankings = Field(alias="categoryPreferences")
    context_preferences: ContextPreferences = Field(alias="contextPreferences")
    user_statements: list[UserStatement] = Field(alias="userStatements")
    existing_activities: list[ActivityFrequency] = Field(alias="existingActivities")
    limitations: list[str]
