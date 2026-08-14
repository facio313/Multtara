import React from 'react';
import './BrandMark.css';

const BrandMark = () => {
  return (
    <span className="brand-mark">
      <img className="brand-mark-icon" src="/logo.svg" alt="" />
      <span className="brand-word">퐁당</span>
    </span>
  );
};

export default BrandMark;
