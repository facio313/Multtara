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
import { personas } from '../data/pongdangData';
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

const questionBank = [
  {
    id: 'scene',
    eyebrow: '첫 장면',
    title: '지금 가장 마음이 가는 물의 장면은?',
    description: '정답은 없어요. 오늘의 기분에 가장 가까운 하나를 골라주세요.',
    options: [
      { persona: 'active', label: '파도를 가르는 순간', detail: '서핑과 래프팅처럼 온몸으로 즐기기' },
      { persona: 'family', label: '아이의 첫 물놀이', detail: '얕고 안전한 물에서 함께 웃기' },
      { persona: 'wellness', label: '고요한 온천의 김', detail: '조용한 풍경 속에서 천천히 쉬기' },
      { persona: 'local', label: '낯선 동네의 물길', detail: '숨은 계곡과 오래된 마을을 발견하기' },
      { persona: 'stay', label: '창밖으로 이어진 풀', detail: '숙소 안에서 여유롭게 머물기' },
    ],
  },
  {
    id: 'priority',
    eyebrow: '선택 기준',
    title: '여행지를 고를 때 가장 먼저 보는 것은?',
    description: '퐁당이 추천 순서를 조정할 때 가장 중요한 기준이 돼요.',
    options: [
      { persona: 'active', label: '오늘의 파도와 유속', detail: '활동하기 좋은 컨디션인지 확인해요' },
      { persona: 'family', label: '안전과 편의시설', detail: '주차, 화장실, 얕은 수심을 살펴요' },
      { persona: 'wellness', label: '한적함과 풍경', detail: '머무는 동안 편안할지를 생각해요' },
      { persona: 'local', label: '그곳만의 이야기', detail: '로컬 문화와 음식까지 궁금해요' },
      { persona: 'stay', label: '쾌적한 실내 동선', detail: '날씨와 이동 피로를 줄이고 싶어요' },
    ],
  },
  {
    id: 'companion',
    eyebrow: '동행',
    title: '이번 물 여행은 누구와 함께하나요?',
    description: '동행에 따라 필요한 안전 정보와 여행의 속도가 달라져요.',
    options: [
      { persona: 'active', label: '도전을 즐기는 친구', detail: '같이 움직이고 기록할 크루와 떠나요' },
      { persona: 'family', label: '아이 또는 부모님', detail: '모두가 무리 없는 하루를 만들어요' },
      { persona: 'wellness', label: '나 자신 또는 가까운 한 사람', detail: '대화와 쉼에 집중하고 싶어요' },
      { persona: 'local', label: '호기심 많은 여행 메이트', detail: '계획 밖의 발견도 함께 즐겨요' },
      { persona: 'stay', label: '편하게 쉬고 싶은 일행', detail: '한 공간에서 각자의 휴식을 누려요' },
    ],
  },
  {
    id: 'pace',
    eyebrow: '여행의 속도',
    title: '가장 이상적인 하루의 리듬은?',
    description: '선호하는 속도에 맞춰 스팟과 주변 동선을 큐레이션해요.',
    options: [
      { persona: 'active', label: '해 뜰 때부터 꽉 채우기', detail: '여러 활동을 이어서 경험해요' },
      { persona: 'family', label: '쉬는 시간을 넉넉하게', detail: '돌발 상황에도 여유 있는 일정이 좋아요' },
      { persona: 'wellness', label: '한 곳에서 오래 머물기', detail: '시간표보다 감각을 따라가요' },
      { persona: 'local', label: '골목마다 잠시 멈추기', detail: '현지인의 추천에 일정을 열어둬요' },
      { persona: 'stay', label: '체크인부터 온전히 쉬기', detail: '숙소 안 경험에 집중하고 싶어요' },
    ],
  },
  {
    id: 'weather',
    eyebrow: '플랜 B',
    title: '비가 예보된 날, 나는 어떻게 할까요?',
    description: '날씨가 바뀌어도 취향에 맞는 대안을 찾을 수 있어요.',
    options: [
      { persona: 'active', label: '안전한 종목으로 바꿔 계속', detail: '컨디션을 읽고 새로운 도전을 찾아요' },
      { persona: 'family', label: '가족이 편한 곳으로 변경', detail: '실내외를 오가기 쉬운 장소를 골라요' },
      { persona: 'wellness', label: '빗소리 좋은 온천으로', detail: '날씨까지 쉼의 분위기로 즐겨요' },
      { persona: 'local', label: '시장과 물길 산책으로', detail: '비가 만든 동네의 표정을 발견해요' },
      { persona: 'stay', label: '실내 풀에서 느긋하게', detail: '이동 없이 완성되는 하루가 좋아요' },
    ],
  },
];

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
        <button className="onboarding-skip" type="button" onClick={() => navigate('/')}>
          건너뛰고 둘러보기
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </header>

      <div className="onboarding-layout">
        <section className="onboarding-intro" aria-labelledby="onboarding-intro-title">
          <p className="onboarding-kicker"><Sparkles size={15} /> TASTE FINDER</p>
          <h1 id="onboarding-intro-title">
            물을 즐기는 방식은<br />
            <span>모두 다르니까.</span>
          </h1>
          <p>
            다섯 번의 가벼운 선택으로 지금의 여행 취향을 찾아드려요.
            이름, 연락처, 위치는 묻지 않아요.
          </p>

          <div className="onboarding-privacy-note">
            <div><Check size={16} aria-hidden="true" /></div>
            <span>
              <strong>취향만, 이 기기에</strong>
              최종 결과 한 가지만 브라우저에 저장됩니다.
            </span>
          </div>

          <div className="onboarding-persona-preview" aria-label="분석 가능한 다섯 가지 물 여행 취향">
            {PERSONA_KEYS.map((key) => (
              <span key={key} title={personaByKey[key].title}>
                {typeof personaByKey[key].icon === 'string' ? personaByKey[key].icon : fallbackPersonas[key].icon}
              </span>
            ))}
          </div>
        </section>

        <section className="onboarding-card" aria-live="polite">
          <div className="onboarding-progress-row">
            <button className="onboarding-back" type="button" onClick={goBack} aria-label="이전 단계">
              <ChevronLeft size={19} aria-hidden="true" />
            </button>
            <div className="onboarding-progress-copy">
              <span>{resultKey ? '분석 완료' : `${step + 1} / ${questionBank.length}`}</span>
              <div
                className="onboarding-progress-track"
                role="progressbar"
                aria-label="취향 분석 진행률"
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
              <p className="onboarding-result-label">당신의 물 여행 취향</p>
              <h2>{selectedPersona.title}</h2>
              <p className="onboarding-result-subtitle">{selectedPersona.subtitle}</p>
              <p className="onboarding-result-description">{selectedPersona.description}</p>

              <div className="onboarding-result-tags" aria-label="추천 취향 태그">
                {(Array.isArray(selectedPersona.tags) ? selectedPersona.tags : []).slice(0, 4).map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
              </div>

              <div className={`onboarding-save-state is-${saveState}`} role="status">
                {saveState === 'saved'
                  ? '이 기기에 취향을 저장했어요. 언제든 MY 퐁당에서 지울 수 있어요.'
                  : '브라우저 저장소를 사용할 수 없어 이번 화면에서만 결과를 보여드려요.'}
              </div>

              <div className="onboarding-result-actions">
                <button className="onboarding-primary-button" type="button" onClick={() => navigate('/')}>
                  맞춤 홈으로 가기
                  <ArrowRight size={17} aria-hidden="true" />
                </button>
                <button
                  className="onboarding-secondary-button"
                  type="button"
                  onClick={() => navigate('/concierge', { state: { personaId: selectedPersona.id } })}
                >
                  <Compass size={17} aria-hidden="true" />
                  AI 컨시어지와 여행 짜기
                </button>
              </div>

              <button className="onboarding-restart" type="button" onClick={restart}>
                <RotateCcw size={15} aria-hidden="true" />
                다시 선택하기
              </button>
            </div>
          ) : (
            <form className="onboarding-question" onSubmit={(event) => { event.preventDefault(); goForward(); }}>
              <fieldset>
                <legend>
                  <span>{currentQuestion.eyebrow}</span>
                  {currentQuestion.title}
                </legend>
                <p className="onboarding-question-description">{currentQuestion.description}</p>

                <div className="onboarding-options">
                  {currentQuestion.options.map((option) => {
                    const isSelected = currentAnswer === option.persona;
                    const optionId = `${currentQuestion.id}-${option.persona}`;

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
                          <strong>{option.label}</strong>
                          <small>{option.detail}</small>
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
                  {step === 0 ? '나가기' : '이전'}
                </button>
                <button className="onboarding-next-button" type="submit" disabled={!currentAnswer}>
                  {step === questionBank.length - 1 ? '내 취향 확인하기' : '다음 질문'}
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
