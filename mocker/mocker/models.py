from django.db.models import Model, CharField, TextField, BooleanField


class StrategyParams(Model):
    name = CharField(
        max_length=50, unique=True, blank=False, null=False
    )

    symbol = CharField(
        max_length=20, blank=False, null=False
    )

    ticker = TextField(
        blank=False, null=False, default='{"ticker":[]}'
    )

    is_infinite = BooleanField(default=False)

    trigger = TextField(
        blank=False, null=False, default='{"buys":1,"sells":0}'
    )

    stop_trigger = TextField(
        blank=False, null=False, default='{"buys":1,"sells":1}'
    )

    description = TextField(
        blank=True, null=False
    )

    def __str__(self):
        return "strategy '%s'" % self.name

    class Meta:
        verbose_name = 'strategy'
        verbose_name_plural = 'strategies'


class ExchangeParams(Model):
    name = CharField(max_length=50, unique=True, blank=False, null=False)

    def __str__(self):
        return "exchange '%s'" % self.name

    class Meta:
        verbose_name = 'exchange'
        verbose_name_plural = 'exchanges'
