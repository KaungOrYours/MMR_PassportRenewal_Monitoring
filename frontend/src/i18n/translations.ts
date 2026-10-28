export type Language = 'en' | 'my'

export const translations = {
  en: {
    appTitle: 'MMR Passport Renewal Monitor',
    heroDescription:
      "Get notified on Telegram the moment your name appears on the Myanmar Embassy Singapore's passport approval or renewal appointment lists.",
    scheduleNote: 'Approval list checks run automatically every 3 hours.',
    peopleUsing: (count: number) => `${count} people are using this service`,
    tabs: { signup: 'Sign Up', lists: 'Lists', alerts: 'Alerts', status: 'Status' },
    form: {
      fullName: 'Full name',
      fullNamePlaceholder: 'As it appears on your passport',
      passportNumber: 'Passport number',
      passportPlaceholder: 'e.g. MG123456',
      telegramIdLabel: 'Your Telegram ID',
      telegramRequired: 'required',
      telegramIdPlaceholder: 'e.g. 123456789',
      connectTelegram: 'Connect Telegram',
      telegramHelpPrefix: 'Tap "Connect Telegram", then tap',
      telegramHelpStart: 'Start',
      telegramHelpSuffix:
        "in the chat that opens — our bot replies instantly with your ID (tap it to copy), paste it above. We'll only message you there, nowhere else.",
      telegramHelpBold: "We can't notify you without this",
      telegramHelpTail:
        "— Telegram doesn't let a bot message someone who hasn't started a chat with it first.",
      note: 'Note (optional)',
      submit: 'Notify me',
      submitting: 'Adding…',
      hintNoTelegram: 'Connect Telegram and enter your ID above to continue.',
      hintNoTerms: 'Please accept the Terms & Conditions to continue.',
      hintNoName: 'Enter your full name to continue.',
      telegramInvalidFormat:
        'That doesn\'t look like a Telegram ID. It should be only numbers (e.g. "123456789") — not a phone number or @username. Tap "Connect Telegram" above and paste the number the bot replies with.',
    },
    terms: {
      heading: 'Terms & Conditions',
      p1: "This is a free, volunteer-run, non-commercial community tool built to help Myanmar citizens in Singapore avoid manually checking the Embassy's approval lists every week. It is",
      p1Bold: 'not affiliated with, endorsed by, or operated on behalf of',
      p1Tail:
        'the Embassy of the Republic of the Union of Myanmar in Singapore, or any Myanmar or Singapore government agency.',
      p2Bold: 'Your data, your responsibility.',
      p2: 'By submitting, you confirm the information is your own, or that you have the consent of the person it belongs to. Your name, passport number, and Telegram ID are stored only to (a) match against the Embassy\'s publicly posted lists and (b) send you a Telegram alert when a match is found. This data is',
      p2Bold2: "never sold, shared with third parties, or used for the developer's personal gain",
      p2Tail: '— it exists solely to operate this notification service for the Myanmar community.',
      p3Bold: 'No guarantee of accuracy.',
      p3: 'Matching relies on OCR and automated text extraction from scanned documents, which can misread names or passport numbers, and the Embassy\'s source lists can change format without notice. This service may miss a match, misfire on a shared name, or experience downtime. It is provided "as is," with no warranty of any kind, and must not be relied on as your sole source of information — always verify independently with the Embassy before taking any action (e.g. travel plans) based on an alert.',
      p4Bold: 'Limitation of liability.',
      p4: 'To the fullest extent permitted under the laws of the Republic of Singapore and the laws of the Republic of the Union of Myanmar, the developer of this tool shall not be liable for any loss, damage, missed appointment, or other consequence arising from reliance on, use of, or inability to use this service. You use this service entirely at your own risk.',
      p5: 'You may remove your data at any time by sending /delete to the bot on Telegram, or by contacting the developer. Continued use of this service is subject to these terms as they may be updated from time to time.',
      checkbox:
        "I have read and agree to the Terms & Conditions above, and I confirm this information is my own (or submitted with the owner's consent).",
    },
    done: {
      onList: "You're on the list.",
      explain:
        "We'll check the embassy's lists automatically and message you on Telegram if your name and passport number appear.",
      sentOk: '✅ A confirmation message was sent to your Telegram — check your chat with the bot.',
      sentFailPrefix: "⚠️ We couldn't send you a Telegram message",
      sentFailHelp:
        'Make sure you\'ve messaged @MMR_PassportRenewalMonitoringBot on Telegram first (send it /start), and that your Telegram ID is correct — get it from @userinfobot. You\'re still on the list either way; you can check your status with the link below.',
      bookmarkNote: 'Bookmark this link to check your status anytime:',
      addAnother: 'Add another person',
    },
  },
  my: {
    appTitle: 'MMR Passport Renewal Monitor',
    heroDescription:
      'စင်ကာပူနိုင်ငံရှိ မြန်မာသံရုံး၏ နိုင်ငံကူးလက်မှတ် (ပတ်စ်ပို့) သက်တမ်းတိုး ခွင့်ပြုချက်စာရင်း သို့မဟုတ် ရက်ချိန်းရရှိသူ စာရင်းများတွင် သင့်အမည် ပါဝင်လာပါက Telegram မှတစ်ဆင့် ချက်ချင်း အသိပေးချက် ပို့ပေးမည့် ဝန်ဆောင်မှု ဖြစ်ပါသည်။',
    scheduleNote: 'စာရင်း နှိုင်းယှဉ်ချက်များကို ၃ နာရီတစ်ကြိမ် အလိုအလျောက် စစ်ဆေးပေးနေပါသည်။',
    peopleUsing: (count: number) => `လူဦးရေ ${count} ဦးက ဤဝန်ဆောင်မှုကို အသုံးပြုနေကြပါသည်။`,
    tabs: {
      signup: 'အကောင့်ဖွင့်ရန်',
      lists: 'စာရင်းများ',
      alerts: 'အသိပေးချက်များ',
      status: 'အခြေအနေ',
    },
    form: {
      fullName: 'အမည်အပြည့်အစုံ',
      fullNamePlaceholder: 'သင့်ပတ်စ်ပို့ပေါ်တွင် ပါရှိသည့်အတိုင်း',
      passportNumber: 'နိုင်ငံကူးလက်မှတ် (ပတ်စ်ပို့) နံပါတ်',
      passportPlaceholder: 'ဥပမာ- MG123456',
      telegramIdLabel: 'သင့် Telegram ID',
      telegramRequired: 'လိုအပ်ပါသည်',
      telegramIdPlaceholder: 'ဥပမာ- 123456789',
      connectTelegram: 'Telegram ချိတ်ဆက်ရန်',
      telegramHelpPrefix: '"Connect Telegram" ကို နှိပ်ပြီး ပွင့်လာသည့် စကားပြောခန်း (Chat) တွင်',
      telegramHelpStart: 'Start',
      telegramHelpSuffix:
        'ကို နှိပ်ပါ။ ကျွန်ုပ်တို့၏ ဘော့တ် (Bot) မှ သင့် ID ကို ချက်ချင်း ပြန်လည် ပို့ပေးပါလိမ့်မည် (ကူးယူရန် ၎င်းကို နှိပ်ပါ)။ ထို့နောက် အထက်ပါ ကွက်လပ်တွင် လာရောက် ထည့်သွင်းပေးပါ။ သင့်အား ဤနေရာမှသာ မက်ဆေ့ချ် ပို့ပေးမည် ဖြစ်ပြီး အခြား မည်သည့်နေရာသို့မျှ ပို့မည် မဟုတ်ပါ။',
      telegramHelpBold: 'ဤသို့ မလုပ်ဆောင်ပါက အကြောင်းကြားပေးနိုင်မည် မဟုတ်ပါ',
      telegramHelpTail:
        '— Telegram ၏ စည်းကမ်းချက်အရ အသုံးပြုသူမှ ဘော့တ်အား စကားပြောခန်း အရင် မစထားပါက ဘော့တ်မှ စတင် မက်ဆေ့ချ် ပို့ခွင့်မရှိပါ။',
      note: 'မှတ်ချက် (ဖြည့်ရန် မလိုပါ)',
      submit: 'အသိပေးပါ',
      submitting: 'ထည့်သွင်းနေသည်…',
      hintNoTelegram: 'ဆက်လက် ဆောင်ရွက်ရန် Telegram ကို ချိတ်ဆက်ပြီး သင့် ID ကို အထက်တွင် ထည့်သွင်းပါ။',
      hintNoTerms: 'ဆက်လက် ဆောင်ရွက်ရန် စည်းမျဉ်းစည်းကမ်းများကို သဘောတူပေးပါ။',
      hintNoName: 'ဆက်လက် ဆောင်ရွက်ရန် သင့်အမည်အပြည့်အစုံကို ထည့်သွင်းပေးပါ။',
      telegramInvalidFormat:
        'ဤသည် Telegram ID ပုံစံ မဟုတ်ပါ။ ဂဏန်းများသက်သက်သာ ဖြစ်ရပါမည် (ဥပမာ- "123456789") — ဖုန်းနံပါတ် သို့မဟုတ် @username မဟုတ်ပါ။ အထက်ရှိ "Connect Telegram" ကို နှိပ်ပြီး ဘော့တ်မှ ပြန်ပို့ပေးသည့် နံပါတ်ကို ကူးယူပါ။',
    },
    terms: {
      heading: 'စည်းမျဉ်းနှင့် စည်းကမ်းချက်များ',
      p1: 'ဤသည်မှာ စင်ကာပူရောက် မြန်မာနိုင်ငံသားများအနေဖြင့် သံရုံး၏ ခွင့်ပြုချက် စာရင်းများကို အပတ်စဉ် လူကိုယ်တိုင် လိုက်လံ ကြည့်ရှုနေရသည့် ဒုက္ခမှ ကင်းဝေးစေရန် ရည်ရွယ်၍ အခမဲ့ ကူညီလုပ်ဆောင်ပေးထားသော လူထုအခြေပြု ဆော့ဖ်ဝဲတူးလ်တစ်ခု ဖြစ်ပါသည်။ ဤဆော့ဖ်ဝဲသည်',
      p1Bold: 'စင်ကာပူနိုင်ငံရှိ ပြည်ထောင်စုသမ္မတ မြန်မာနိုင်ငံတော် သံရုံး၊ သို့မဟုတ် မြန်မာနှင့် စင်ကာပူ အစိုးရ အေဂျင်စီ တစ်ခုခုနှင့် လုံးဝ သက်ဆိုင်ခြင်း၊ ထောက်ခံထားခြင်း သို့မဟုတ် ပူးပေါင်း လုပ်ဆောင်ခြင်း မရှိပါ',
      p1Tail: '',
      p2Bold: 'သင့်အချက်အလက်၊ သင့်တာဝန်',
      p2: 'ဤနေရာတွင် အချက်အလက်များ တင်ပြခြင်းဖြင့် ဖြည့်သွင်းထားသော အချက်အလက်များသည် သင်၏ ကိုယ်ပိုင်အချက်အလက်များ ဖြစ်ကြောင်း သို့မဟုတ် သက်ဆိုင်ရာ ပိုင်ရှင်၏ ခွင့်ပြုချက်ကို ရယူထားပြီး ဖြစ်ကြောင်း အတည်ပြုပါသည်။ သင့်အမည်၊ ပတ်စ်ပို့နံပါတ်နှင့် Telegram ID တို့ကို (က) သံရုံးမှ အများပြည်သူ သိရှိနိုင်ရန် ထုတ်ပြန်ထားသော စာရင်းများနှင့် တိုက်ဆိုင် စစ်ဆေးရန်နှင့် (ခ) ကိုက်ညီမှု ရှိပါက Telegram မှတစ်ဆင့် အသိပေးချက် ပို့ပေးရန်အတွက်သာ သိမ်းဆည်းထားမည် ဖြစ်ပါသည်။ ဤအချက်အလက်များကို',
      p2Bold2: 'မည်သည့်အခါမျှ ရောင်းချခြင်း၊ ပြင်ပ တတိယလူထံ မျှဝေခြင်း သို့မဟုတ် ဖန်တီးသူ၏ ကိုယ်ကျိုးအတွက် အသုံးချခြင်း လုံးဝ မရှိပါ',
      p2Tail: '— မြန်မာ အသိုင်းအဝိုင်းအတွက် အသိပေးသည့် ဝန်ဆောင်မှု ပံ့ပိုးရန် သီးသန့် အသုံးပြုခြင်း ဖြစ်ပါသည်။',
      p3Bold: 'တိကျမှန်ကန်မှု အာမမခံပါ',
      p3: 'အချက်အလက် တိုက်ဆိုင် စစ်ဆေးခြင်းသည် စကင်ဖတ်ထားသော စာရွက်စာတမ်းများမှ OCR (စာသား အလိုအလျောက် ထုတ်ယူသည့် စနစ်) ကို အသုံးပြုထားခြင်း ဖြစ်သည့်အတွက် အမည် သို့မဟုတ် ပတ်စ်ပို့နံပါတ်များကို လွဲမှား စစ်ဆေးမိခြင်း သို့မဟုတ် သံရုံး၏ မူရင်း စာရင်း ပုံစံများ အကြို အကြောင်းမကြားဘဲ ပြောင်းလဲသွားခြင်းမျိုး ရှိနိုင်ပါသည်။ ဤဝန်ဆောင်မှုတွင် စာရင်း လွဲချော်ခြင်း၊ အမည်တူ မှားယွင်း အကြောင်းကြားမိခြင်း သို့မဟုတ် စနစ် ခေတ္တ ရပ်တန့်ခြင်းများ ဖြစ်ပေါ်နိုင်ပါသည်။ ဤဝန်ဆောင်မှုကို "ရှိသည့်အတိုင်း" (As is) ပံ့ပိုးထားခြင်း ဖြစ်ပြီး မည်သည့် အာမခံချက်မှ မရှိပါ။ ထို့ကြောင့် အသိပေးချက် တစ်ခုတည်းကိုသာ အခြေခံ၍ (ဥပမာ- ခရီးသွား အစီအစဉ်များ ဆွဲခြင်း စသည်ဖြင့်) ဆုံးဖြတ်ချက် မချပါနှင့်။ မည်သည့် ကိစ္စမဆို မလုပ်ဆောင်မီ သံရုံးတွင် သီးခြား လွတ်လပ်စွာ အမြဲတမ်း ပြန်လည် အတည်ပြုပါ။',
      p4Bold: 'တာဝန်ယူမှု ကန့်သတ်ချက်',
      p4: 'စင်ကာပူနိုင်ငံနှင့် ပြည်ထောင်စုသမ္မတ မြန်မာနိုင်ငံတော်တို့၏ တည်ဆဲ ဥပဒေများအရ ခွင့်ပြုထားသည့် အမြင့်ဆုံး အတိုင်းအတာအထိ ဤတူးလ်ကို အသုံးပြုခြင်း၊ အားကိုးခြင်း သို့မဟုတ် အသုံးပြု၍ မရခြင်းတို့ကြောင့် ဖြစ်ပေါ်လာသည့် မည်သည့် ဆုံးရှုံးမှု၊ ထိခိုက်မှု၊ ရက်ချိန်း လွတ်သွားမှု သို့မဟုတ် အခြား နောက်ဆက်တွဲ အကျိုးဆက်များအတွက်မဆို ဤတူးလ် ဖန်တီးသူတွင် မည်သည့် တာဝန်မျှ မရှိပါ။ ဤဝန်ဆောင်မှုကို အသုံးပြုခြင်းသည် သင့်ကိုယ်ပိုင် တာဝန် ဖြစ်ပါသည်။',
      p5: 'Telegram ဘော့တ်ထံ /delete ကို ပို့၍သော်လည်းကောင်း၊ ဖန်တီးသူထံ တိုက်ရိုက် ဆက်သွယ်၍သော်လည်းကောင်း သင့်အချက်အလက်များကို အချိန်မရွေး ဖျက်ပစ်နိုင်ပါသည်။ ဤဝန်ဆောင်မှုကို ဆက်လက် အသုံးပြုခြင်းသည် အချိန်နှင့်အမျှ ပြောင်းလဲနိုင်သော စည်းကမ်းချက်များကို လက်ခံ လိုက်နာသည်ဟု မှတ်ယူပါမည်။',
      checkbox:
        'အထက်ပါ စည်းမျဉ်းနှင့် စည်းကမ်းချက်များကို ဖတ်ရှုပြီး သဘောတူပါသည်၊ အချက်အလက်များသည် ကျွန်ုပ်၏ ကိုယ်ပိုင် ဖြစ်ကြောင်း (သို့မဟုတ် ပိုင်ရှင်၏ ခွင့်ပြုချက် ရယူထားကြောင်း) အတည်ပြုပါသည်။',
    },
    done: {
      onList: 'သင့်အား စာရင်းသွင်းပြီးပါပြီ။',
      explain:
        'ကျွန်ုပ်တို့သည် သံရုံး၏ စာရင်းများကို အလိုအလျောက် စစ်ဆေးပေးနေမည်ဖြစ်ပြီး၊ သင့်အမည်နှင့် ပတ်စ်ပို့နံပါတ် ပါဝင်လာပါက Telegram မှတစ်ဆင့် အကြောင်းကြားပါမည်။',
      sentOk: '✅ သင့် Telegram သို့ အတည်ပြုမက်ဆေ့ချ် ပို့ပြီးပါပြီ — ဘော့တ်နှင့် သင့်စကားပြောခန်းကို စစ်ဆေးကြည့်ပါ။',
      sentFailPrefix: '⚠️ သင့်ထံ Telegram မက်ဆေ့ချ် ပို့နိုင်ခြင်း မရှိပါ',
      sentFailHelp:
        '@MMR_PassportRenewalMonitoringBot ကို Telegram တွင် ဦးစွာ /start ပို့ထားပြီးကြောင်း သေချာပါစေ၊ ထို့ပြင် သင့် Telegram ID မှန်ကန်ကြောင်းလည်း စစ်ဆေးပါ — ID ကို @userinfobot မှ ရယူနိုင်ပါသည်။ မည်သို့ပင်ဖြစ်စေ သင့်အား စာရင်းတွင် ထည့်သွင်းပြီးပါပြီ၊ အောက်ပါလင့်ခ်ဖြင့် သင့်အခြေအနေကို စစ်ဆေးနိုင်ပါသည်။',
      bookmarkNote: 'ဤလင့်ခ်ကို မှတ်သားထားပြီး အချိန်မရွေး သင့်အခြေအနေကို စစ်ဆေးနိုင်ပါသည်-',
      addAnother: 'နောက်တစ်ဦး ထပ်ထည့်ရန်',
    },
  },
} as const

export type TranslationShape = typeof translations.en
