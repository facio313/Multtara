import { useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  Compass,
  Droplets,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import LocaleSelector from '../components/layout/LocaleSelector';
import { personas } from '../data/pongdangData';
import { useI18n } from '../i18n';
import './OnboardingPage.css';

const PREFERENCE_STORAGE_KEY = 'pongdang:persona-preference';
const PERSONA_KEYS = ['active', 'family', 'wellness', 'local', 'stay'];

const fallbackPersonas = {
  active: {
    id: 'active',
    title: '파도를 좇는 액티브 트래블러',
    subtitle: '도전과 속도가 여행의 에너지',
    description: '서핑, 래프팅, 계곡 탐험처럼 몸으로 물을 만나는 순간에 끌려요.',
    tags: ['액티비티', '서핑', '도전'],
    icon: '🏄',
  },
  family: {
    id: 'family',
    title: '안심부터 챙기는 패밀리 리스너',
    subtitle: '함께라서 더 편안한 물 여행',
    description: '얕은 물, 안전시설, 짧은 동선처럼 온 가족이 편한 조건을 먼저 살펴요.',
    tags: ['아이와 함께', '안전', '편의시설'],
    icon: '🛟',
  },
  wellness: {
    id: 'wellness',
    title: '쉼을 수집하는 웰니스 힐러',
    subtitle: '잔잔한 물에서 되찾는 나의 리듬',
    description: '온천과 호수, 조용한 물멍처럼 몸과 마음을 천천히 회복하는 여행을 좋아해요.',
    tags: ['온천', '물멍', '한적함'],
    icon: '♨️',
  },
  local: {
    id: 'local',
    title: '동네의 물길을 읽는 로컬 탐험가',
    subtitle: '잘 알려지지 않은 이야기를 따라서',
    description: '시장, 골목, 로컬 미식과 이어진 숨은 물 명소를 발견하는 재미를 찾아요.',
    tags: ['로컬', '숨은 명소', '미식'],
    icon: '🧭',
  },
  stay: {
    id: 'stay',
    title: '날씨 걱정 없는 인도어 스테이어',
    subtitle: '머무는 공간 자체가 여행',
    description: '실내 스파, 인피니티풀, 워터파크처럼 편안하고 완성도 높은 체류를 선호해요.',
    tags: ['스테이', '실내', '스파'],
    icon: '🏨',
  },
};

const personaAliases = {
  active: ['active', 'activity', 'adventure', '액티브', '모험', '도전'],
  family: ['family', '가족', '패밀리'],
  wellness: ['wellness', 'healing', 'relax', '웰니스', '힐링'],
  local: ['local', '로컬', '지역'],
  stay: ['stay', 'indoor', 'resort', '스테이', '실내'],
};

const questionBank = ['scene', 'priority', 'companion', 'pace', 'weather'].map((id) => ({
  id,
  options: PERSONA_KEYS.map((persona) => ({ persona })),
}));

function normalizeText(value) {
  return String(value ?? '').trim().toLowerCase();
}

function findPersonaForKey(key) {
  if (!Array.isArray(personas)) return fallbackPersonas[key];

  const matchedPersona = personas.find((persona) => {
    const searchable = normalizeText(`${persona?.id} ${persona?.title} ${persona?.subtitle}`);
    return personaAliases[key].some((alias) => searchable.includes(normalizeText(alias)));
  });

  return matchedPersona || fallbackPersonas[key];
}

function calculatePersonaKey(answers) {
  const scores = Object.fromEntries(PERSONA_KEYS.map((key) => [key, 0]));
  answers.forEach((answer) => {
    if (answer && answer in scores) scores[answer] += 1;
  });

  const firstChoice = answers.find(Boolean) || 'wellness';
  return PERSONA_KEYS.reduce(
    (winner, key) => (scores[key] > scores[winner] ? key : winner),
    firstChoice,
  );
}

function savePreference(personaId) {
  try {
    window.localStorage.setItem(PREFERENCE_STORAGE_KEY, String(personaId));
    return true;
  } catch {
    return false;
  }
}

function OnboardingPage() {
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState(() => Array(questionBank.length).fill(null));
  const [resultKey, setResultKey] = useState(null);
  const [saveState, setSaveState] = useState('idle');

  const personaByKey = useMemo(
    () => Object.fromEntries(PERSONA_KEYS.map((key) => [key, findPersonaForKey(key)])),
    [],
  );

  const currentQuestion = questionBank[step];
  const currentAnswer = answers[step];
  const selectedPersona = resultKey ? personaByKey[resultKey] : null;
  const progress = resultKey ? 100 : ((step + 1) / questionBank.length) * 100;

  const chooseAnswer = (personaKey) => {
    setAnswers((currentAnswers) => currentAnswers.map((answer, index) => (
      index === step ? personaKey : answer
    )));
  };

  const showResult = () => {
    const nextResultKey = calculatePersonaKey(answers);
    const nextPersona = personaByKey[nextResultKey];
    const didSave = savePreference(nextPersona?.id || nextResultKey);

    setResultKey(nextResultKey);
    setSaveState(didSave ? 'saved' : 'unavailable');
  };

  const goForward = () => {
    if (!currentAnswer) return;
    if (step === questionBank.length - 1) {
      showResult();
      return;
    }
    setStep((currentStep) => currentStep + 1);
  };

  const goBack = () => {
    if (resultKey) {
      setResultKey(null);
      setStep(questionBank.length - 1);
      setSaveState('idle');
      return;
    }

    if (step === 0) {
      navigate('/');
      return;
    }

    setStep((currentStep) => currentStep - 1);
  };

  const restart = () => {
    setAnswers(Array(questionBank.length).fill(null));
    setResultKey(null);
    setSaveState('idle');
    setStep(0);
  };

  return (
    <div className="onboarding-page">
      <div className="onboarding-orb onboarding-orb-one" aria-hidden="true" />
      <div className="onboarding-orb onboarding-orb-two" aria-hidden="true" />

      <header className="onboarding-topbar">
        <button className="onboarding-brand" type="button" onClick={() => navigate('/')}>
          <span><Droplets size={19} aria-hidden="true" /></span>
          <strong>퐁당</strong>
          <small>PONGDANG</small>
        </button>
        <div className="onboarding-topbar-actions">
          <LocaleSelector className="onboarding-locale-selector" />
          <button className="onboarding-skip" type="button" onClick={() => navigate('/')}>
            {t('onboarding.skip')}
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="onboarding-layout">
        <section className="onboarding-intro" aria-labelledby="onboarding-intro-title">
          <p className="onboarding-kicker"><Sparkles size={15} /> TASTE FINDER</p>
          <h1 id="onboarding-intro-title">{t('onboarding.hero.title')}</h1>
          <p>{t('onboarding.hero.description')}</p>

          <div className="onboarding-privacy-note">
            <div><Check size={16} aria-hidden="true" /></div>
            <span>
              <strong>{t('onboarding.privacy.title')}</strong>
              {t('onboarding.privacy.description')}
            </span>
          </div>

          <div className="onboarding-persona-preview" aria-label={t('onboarding.preview')}>
            {PERSONA_KEYS.map((key) => (
              <span key={key} title={t(`persona.${key === 'stay' ? 'indoor' : key}.title`)}>
                {typeof personaByKey[key].icon === 'string' ? personaByKey[key].icon : fallbackPersonas[key].icon}
              </span>
            ))}
          </div>
        </section>

        <section className="onboarding-card" aria-live="polite">
          <div className="onboarding-progress-row">
            <button className="onboarding-back" type="button" onClick={goBack} aria-label={t('onboarding.back')}>
              <ChevronLeft size={19} aria-hidden="true" />
            </button>
            <div className="onboarding-progress-copy">
              <span>{resultKey ? t('onboarding.complete') : `${step + 1} / ${questionBank.length}`}</span>
              <div
                className="onboarding-progress-track"
                role="progressbar"
                aria-label={t('onboarding.progress')}
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={Math.round(progress)}
              >
                <span style={{ width: `${progress}%` }} />
              </div>
            </div>
          </div>

          {selectedPersona ? (
            <div className="onboarding-result">
              <div className="onboarding-result-mark" aria-hidden="true">
                {typeof selectedPersona.icon === 'string' ? selectedPersona.icon : fallbackPersonas[resultKey].icon}
              </div>
              <p className="onboarding-result-label">{t('onboarding.result.label')}</p>
              <h2>{t(`persona.${resultKey === 'stay' ? 'indoor' : resultKey}.title`)}</h2>
              <p className="onboarding-result-subtitle">{t(`persona.${resultKey === 'stay' ? 'indoor' : resultKey}.subtitle`)}</p>
              <p className="onboarding-result-description">{t(`persona.${resultKey === 'stay' ? 'indoor' : resultKey}.description`)}</p>

              <div className="onboarding-result-tags" aria-label={t('onboarding.result.tags')}>
                {(locale === 'ko'
                  ? (Array.isArray(selectedPersona.tags) ? selectedPersona.tags : []).slice(0, 4)
                  : [t(`persona.${resultKey === 'stay' ? 'indoor' : resultKey}.subtitle`)]
                ).map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
              </div>

              <div className={`onboarding-save-state is-${saveState}`} role="status">
                {saveState === 'saved'
                  ? t('onboarding.save.saved')
                  : t('onboarding.save.unavailable')}
              </div>

              <div className="onboarding-result-actions">
                <button className="onboarding-primary-button" type="button" onClick={() => navigate('/')}>
                  {t('onboarding.cta.home')}
                  <ArrowRight size={17} aria-hidden="true" />
                </button>
                <button
                  className="onboarding-secondary-button"
                  type="button"
                  onClick={() => navigate('/concierge', { state: { personaId: selectedPersona.id } })}
                >
                  <Compass size={17} aria-hidden="true" />
                  {t('onboarding.cta.concierge')}
                </button>
              </div>

              <button className="onboarding-restart" type="button" onClick={restart}>
                <RotateCcw size={15} aria-hidden="true" />
                {t('onboarding.cta.restart')}
              </button>
            </div>
          ) : (
            <form className="onboarding-question" onSubmit={(event) => { event.preventDefault(); goForward(); }}>
              <fieldset>
                <legend>
                  <span>{t(`onboarding.question.${currentQuestion.id}.eyebrow`)}</span>
                  {t(`onboarding.question.${currentQuestion.id}.title`)}
                </legend>
                <p className="onboarding-question-description">{t(`onboarding.question.${currentQuestion.id}.description`)}</p>

                <div className="onboarding-options">
                  {currentQuestion.options.map((option) => {
                    const isSelected = currentAnswer === option.persona;
                    const optionId = `${currentQuestion.id}-${option.persona}`;
                    const optionMessageKey = `onboarding.option.${currentQuestion.id}.${option.persona}`;

                    return (
                      <label className={`onboarding-option${isSelected ? ' is-selected' : ''}`} htmlFor={optionId} key={option.persona}>
                        <input
                          id={optionId}
                          type="radio"
                          name={currentQuestion.id}
                          value={option.persona}
                          checked={isSelected}
                          onChange={() => chooseAnswer(option.persona)}
                        />
                        <span className="onboarding-option-icon" aria-hidden="true">
                          {typeof personaByKey[option.persona].icon === 'string'
                            ? personaByKey[option.persona].icon
                            : fallbackPersonas[option.persona].icon}
                        </span>
                        <span className="onboarding-option-copy">
                          <strong>{t(`${optionMessageKey}.label`)}</strong>
                          <small>{t(`${optionMessageKey}.detail`)}</small>
                        </span>
                        <span className="onboarding-option-check" aria-hidden="true">
                          <Check size={15} />
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <div className="onboarding-controls">
                <button className="onboarding-previous-button" type="button" onClick={goBack}>
                  <ArrowLeft size={16} aria-hidden="true" />
                  {step === 0 ? t('onboarding.cta.exit') : t('onboarding.cta.previous')}
                </button>
                <button className="onboarding-next-button" type="submit" disabled={!currentAnswer}>
                  {step === questionBank.length - 1 ? t('onboarding.cta.result') : t('onboarding.cta.next')}
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}

export default OnboardingPage;
