from module.base.button import Button
from module.base.template import Template

# Run `python -m dev_tools.button_extract` after updating RateArea_Get.png to refresh color/area.
RATE_AREA_GET = Button(
    area={'cn': (1030, 370, 1100, 470)},
    color={'cn': (180, 165, 130)},
    button={'cn': (1030, 370, 1100, 470)},
    file={'cn': './assets/cn/BoatRate/RateArea_Get.png'},
)
